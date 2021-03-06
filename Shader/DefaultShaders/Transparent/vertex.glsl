#version 410

#pragma include "Includes/Configuration.include"
#pragma include "Includes/Structures/VertexOutput.struct"
#pragma include "Includes/Structures/PandaMaterial.struct"

// Matrices
uniform mat4 trans_model_to_world;
uniform mat4 tpose_world_to_model;

// Material properties
in vec4 p3d_Vertex;
in vec3 p3d_Normal;

in vec2 p3d_MultiTexCoord0;

// Outputs
layout(location=0) out VertexOutput vOutput;

uniform PandaMaterial p3d_Material;
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform vec4 p3d_ColorScale;

void main() {

    // Transform normal to world space
    vOutput.normalWorld   = normalize(tpose_world_to_model * vec4(p3d_Normal, 0) ).xyz;

    // Transform position to world space
    vOutput.positionWorld = (trans_model_to_world * p3d_Vertex).xyz;

    // Pass texcoord to fragment shader
    vOutput.texcoord = p3d_MultiTexCoord0.xy;

    // Also pass diffuse to fragment shader
    vOutput.materialDiffuse = p3d_Material.diffuse * p3d_ColorScale;
    vOutput.materialSpecular = p3d_Material.specular;
    vOutput.materialAmbient = p3d_Material.ambient.z;

    // Transform vertex to window space
    // Only required when not using tesselation shaders
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}

