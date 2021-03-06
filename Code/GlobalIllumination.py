
from panda3d.core import Texture, NodePath, ShaderAttrib, Vec4, Vec3
from panda3d.core import Shader, SamplerState
from panda3d.core import Vec2, LMatrix4f, LVecBase3i, Camera, Mat4
from panda3d.core import Mat4, OmniBoundingVolume, OrthographicLens
from panda3d.core import BoundingBox, Point3, CullFaceAttrib, PTAMat4
from panda3d.core import DepthTestAttrib, PTALVecBase3f, ComputeNode, PTALVecBase2f
from direct.stdpy.file import isfile, open, join

from Globals import Globals
from DebugObject import DebugObject
from LightType import LightType
from GUI.BufferViewerGUI import BufferViewerGUI
from RenderTarget import RenderTarget
from GIHelperLight import GIHelperLight
from LightType import LightType
from SettingsManager import SettingsManager
from MemoryMonitor import MemoryMonitor

from RenderPasses.GlobalIlluminationPass import GlobalIlluminationPass
from RenderPasses.VoxelizePass import VoxelizePass

import time
import math

class GlobalIllumination(DebugObject):

    """ This class handles the global illumination processing. To process the
    global illumination, the scene is first rasterized from 3 directions, and 
    a 3D voxel grid is created. After that, the mipmaps of the voxel grid are
    generated. The final shader then performs voxel cone tracing to compute 
    an ambient, diffuse and specular term.

    The gi is split over several frames to reduce the computation cost. Currently
    there are 5 different steps, split over 4 frames:

    Frame 1: 
        - Rasterize the scene from the x-axis

    Frame 2:
        - Rasterize the scene from the y-axis

    Frame 3: 
        - Rasterize the scene from the z-axis

    Frame 4:
        - Copy the generated temporary voxel grid into a stable voxel grid
        - Generate the mipmaps for that stable voxel grid using a gaussian filter

    In the final pass the stable voxel grid is sampled. The voxel tracing selects
    the mipmap depending on the cone size. This enables small scale details as well
    as blurry reflections and low-frequency ao / diffuse. For performance reasons,
    the final pass is executed at half window resolution and then bilateral upscaled.
    """


    def __init__(self, pipeline):
        DebugObject.__init__(self, "GlobalIllumnination")
        self.pipeline = pipeline

        # Fetch the scene data
        self.targetCamera = Globals.base.cam
        self.targetSpace = Globals.base.render

        # Store grid size in world space units
        # This is the half voxel grid size
        self.voxelGridSizeWS = Vec3(60)

        # When you change this resolution, you have to change it in Shader/GI/ConvertGrid.fragment aswell
        self.voxelGridResolution = LVecBase3i(256)

        self.targetLight = None
        self.helperLight = None
        self.ptaGridPos = PTALVecBase3f.emptyArray(1)
        self.gridPos = Vec3(0)

        # Create ptas 

        self.ptaLightUVStart = PTALVecBase2f.emptyArray(1)
        self.ptaLightMVP = PTAMat4.emptyArray(1)
        self.ptaVoxelGridStart = PTALVecBase3f.emptyArray(1)
        self.ptaVoxelGridEnd = PTALVecBase3f.emptyArray(1)
        self.ptaLightDirection = PTALVecBase3f.emptyArray(1)

        self.targetSpace.setShaderInput("giLightUVStart", self.ptaLightUVStart)
        self.targetSpace.setShaderInput("giLightMVP", self.ptaLightMVP)
        self.targetSpace.setShaderInput("giVoxelGridStart", self.ptaVoxelGridStart)
        self.targetSpace.setShaderInput("giVoxelGridEnd", self.ptaVoxelGridEnd)
        self.targetSpace.setShaderInput("giLightDirection", self.ptaLightDirection)

    def setTargetLight(self, light):
        """ Sets the sun light which is the main source of GI. Only that light
        casts gi. """
        if light.getLightType() != LightType.Directional:
            self.error("setTargetLight expects a directional light!")
            return

        self.targetLight = light
        self._createHelperLight()

    def _createHelperLight(self):
        """ Creates the helper light. We can't use the main directional light
        because it uses PSSM, so we need an extra shadow map that covers the
        whole voxel grid. """
        self.helperLight = GIHelperLight()
        self.helperLight.setPos(Vec3(50,50,100))
        self.helperLight.setShadowMapResolution(512)
        self.helperLight.setFilmSize(math.sqrt( (self.voxelGridSizeWS.x**2) * 2) * 2 )
        self.helperLight.setCastsShadows(True)
        self.pipeline.addLight(self.helperLight)
        self.targetSpace.setShaderInput("giLightUVSize", 
            float(self.helperLight.shadowResolution) / self.pipeline.settings.shadowAtlasSize)
        self._updateGridPos()

    def setup(self):
        """ Setups everything for the GI to work """


        # Create the voxelize pass which is used to voxelize the scene from
        # several directions
        self.voxelizePass = VoxelizePass()
        self.voxelizePass.setVoxelGridResolution(self.voxelGridResolution)
        self.voxelizePass.setVoxelGridSize(self.voxelGridSizeWS)
        self.voxelizePass.initVoxelStorage()
        self.pipeline.getRenderPassManager().registerPass(self.voxelizePass)

        # Create 3D Texture which is a copy of the voxel generation grid but
        # stable, as the generation grid is updated part by part and that would 
        # lead to flickering
        self.voxelStableTex = Texture("VoxelsStable")
        self.voxelStableTex.setup3dTexture(self.voxelGridResolution.x, self.voxelGridResolution.y, 
                                            self.voxelGridResolution.z, Texture.TFloat, Texture.FRgba8)

        # Set appropriate filter types:
        # The stable texture has mipmaps, which are generated during the process.
        # This is required for cone tracing.
        self.voxelStableTex.setMagfilter(SamplerState.FTLinear)
        self.voxelStableTex.setMinfilter(SamplerState.FTLinearMipmapLinear)
        self.voxelStableTex.setWrapU(SamplerState.WMBorderColor)
        self.voxelStableTex.setWrapV(SamplerState.WMBorderColor)
        self.voxelStableTex.setWrapW(SamplerState.WMBorderColor)
        self.voxelStableTex.setBorderColor(Vec4(0,0,0,0))

        MemoryMonitor.addTexture("Voxel Grid Texture", self.voxelStableTex)

        # Setups the render target to convert the voxel grid
        self.convertBuffer = RenderTarget("VoxelConvertBuffer")
        self.convertBuffer.setSize(self.voxelGridResolution.x, self.voxelGridResolution.y)
        self.convertBuffer.setColorWrite(False)
        # self.convertBuffer.addColorTexture()
        self.convertBuffer.prepareOffscreenBuffer()
        self.convertBuffer.setShaderInput("src", self.voxelizePass.getVoxelTex())
        self.convertBuffer.setShaderInput("dest", self.voxelStableTex)
        self.convertBuffer.setActive(False)

        # Store the frame index, we need that to decide which step we are currently
        # doing
        self.frameIndex = 0


        # Create the various render targets to generate the mipmaps of the stable voxel grid
        self.mipmapTargets = []
        computeSize = LVecBase3i(self.voxelGridResolution)
        currentMipmap = 0
        while computeSize.z > 1:
            computeSize /= 2
            target = RenderTarget("GIMiplevel" + str(currentMipmap))
            target.setSize(computeSize.x, computeSize.y)
            target.setColorWrite(False)
            # target.addColorTexture()
            target.prepareOffscreenBuffer()
            target.setActive(False)
            target.setShaderInput("sourceMipmap", currentMipmap)
            target.setShaderInput("source", self.voxelStableTex)
            target.setShaderInput("dest", self.voxelStableTex, False, True, -1, currentMipmap + 1)
            self.mipmapTargets.append(target)
            currentMipmap += 1


        # Create the final gi pass
        self.finalPass = GlobalIlluminationPass()
        self.pipeline.getRenderPassManager().registerPass(self.finalPass)
        self.pipeline.getRenderPassManager().registerDynamicVariable("giVoxelGridData", self.bindTo)

    def _createConvertShader(self):
        """ Loads the shader for converting the voxel grid """
        shader = Shader.load(Shader.SLGLSL, 
            "Shader/DefaultPostProcess.vertex", "Shader/GI/ConvertGrid.fragment")
        self.convertBuffer.setShader(shader)

    def _createGenerateMipmapsShader(self):
        """ Loads the shader for generating the voxel grid mipmaps """
        computeSizeZ = self.voxelGridResolution.z
        for child in self.mipmapTargets:
            computeSizeZ /= 2
            shader = Shader.load(Shader.SLGLSL, 
                "Shader/DefaultPostProcess.vertex", 
                "Shader/GI/GenerateMipmaps/" + str(computeSizeZ) + ".fragment")
            child.setShader(shader)

    def reloadShader(self):
        """ Reloads all shaders and updates the voxelization camera state aswell """
        self._createGenerateMipmapsShader()
        self._createConvertShader()

    def _updateGridPos(self):
        """ Computes the new center of the voxel grid. The center pos is also
        snapped, to avoid flickering. """

        # It is important that the grid is snapped, otherwise it will flicker 
        # while the camera moves. When using a snap of 32, everything until
        # the log2(32) = 5th mipmap is stable. 
        snap = 32.0
        stepSizeX = float(self.voxelGridSizeWS.x * 2.0) / float(self.voxelGridResolution.x) * snap
        stepSizeY = float(self.voxelGridSizeWS.y * 2.0) / float(self.voxelGridResolution.y) * snap
        stepSizeZ = float(self.voxelGridSizeWS.z * 2.0) / float(self.voxelGridResolution.z) * snap

        self.gridPos = self.targetCamera.getPos(self.targetSpace)
        self.gridPos.x -= self.gridPos.x % stepSizeX
        self.gridPos.y -= self.gridPos.y % stepSizeY
        self.gridPos.z -= self.gridPos.z % stepSizeZ

    def update(self):
        """ Processes the gi, this method is called every frame """

        # With no light, there is no gi
        if self.targetLight is None:
            self.error("The GI cannot work without a directional target light! Set one "
                "with renderPipeline.setGILightSource(directionalLight) first!")
            return

        # Fetch current light direction
        direction = self.targetLight.getDirection()

        if self.frameIndex == 0:
            # Step 1: Voxelize scene from the x-Axis
            for child in self.mipmapTargets:
                child.setActive(False)

            self.convertBuffer.setActive(False)

            # Clear the old data in generation texture 
            self.voxelizePass.clearGrid()
            self.voxelizePass.voxelizeSceneFromDirection(self.gridPos, "x")

            # Set required inputs
            self.ptaLightUVStart[0] = self.helperLight.shadowSources[0].getAtlasPos()
            self.ptaLightMVP[0] = self.helperLight.shadowSources[0].mvp
            self.ptaVoxelGridStart[0] = self.gridPos - self.voxelGridSizeWS
            self.ptaVoxelGridEnd[0] = self.gridPos + self.voxelGridSizeWS
            self.ptaLightDirection[0] = direction

        elif self.frameIndex == 1:

            # Step 2: Voxelize scene from the y-Axis
            self.voxelizePass.voxelizeSceneFromDirection(self.gridPos, "y")

        elif self.frameIndex == 2:

            # Step 3: Voxelize the scene from the z-Axis 
            self.voxelizePass.voxelizeSceneFromDirection(self.gridPos, "z")
            
            # Update helper light, so that it is at the right position when Step 1
            # starts again 
            self.helperLight.setPos(self.gridPos)
            self.helperLight.setDirection(direction)

        elif self.frameIndex == 3:

            # Step 4: Extract voxel grid and generate mipmaps
            self.voxelizePass.setActive(False)
            self.convertBuffer.setActive(True)

            for child in self.mipmapTargets:
                child.setActive(True)

            # We are done now, update the inputs
            self.ptaGridPos[0] = Vec3(self.gridPos)
            self._updateGridPos()

        # Increase frame index
        self.frameIndex += 1
        self.frameIndex = self.frameIndex % 4

    def bindTo(self, node, prefix):
        """ Binds all required shader inputs to a target to compute / display
        the global illumination """

        normFactor = Vec3(1.0,
                float(self.voxelGridResolution.y) / float(self.voxelGridResolution.x) * self.voxelGridSizeWS.y / self.voxelGridSizeWS.x,
                float(self.voxelGridResolution.z) / float(self.voxelGridResolution.x) * self.voxelGridSizeWS.z / self.voxelGridSizeWS.x)
        node.setShaderInput(prefix + ".gridPos", self.ptaGridPos)
        node.setShaderInput(prefix + ".gridHalfSize", self.voxelGridSizeWS)
        node.setShaderInput(prefix + ".gridResolution", self.voxelGridResolution)
        node.setShaderInput(prefix + ".voxels", self.voxelStableTex)
        node.setShaderInput(prefix + ".voxelNormFactor", normFactor)
        node.setShaderInput(prefix + ".geometry", self.voxelStableTex)

