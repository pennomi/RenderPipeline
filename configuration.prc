
# No stack trace on assertion
assert-abort #f

# File system should be case sensitive
vfs-case-sensitive #t

# Animations on the gpu
#hardware-animated-vertices #t

# Show error on dll loading
# show-dll-error-dialog #t

# Trying this for performance
# uniquify-matrix #f

# Garbarge collection
garbage-collect-states #f
garbage-collect-states-rate 1.0


transform-cache #t
state-cache #f


# Trying this for performance
# uniquify-transforms #f
# uniquify-states #f 
# uniquify-attribs #f

# Faster texture loading
# fake-texture-image someimage.png

# Frame rate meter
frame-rate-meter-milliseconds #t
frame-rate-meter-update-interval 1.0
frame-rate-meter-text-pattern %0.2f fps
frame-rate-meter-ms-text-pattern %0.3f ms
frame-rate-meter-layer-sort 1000
frame-rate-meter-scale 0.04
frame-rate-meter-side-margins 0.4


# Pstats
pstats-target-frame-rate 60.0
pstats-unused-states #t

# For smoother animations
# even-animation #t


# Threading
# threading-model T1/T2/T3


# Try for better performance
# prefer-single-buffer #t

# No stencil
support-stencil #f
framebuffer-stencil #f


# Undecorated?
# undecorated #t

# Not resizable
win-fixed-size #t
win-size 1600 960
# win-size 1280 720

# Icon
# icon-filename lalala

# Show custom cursor
# cursor-filename lalala

# The title of the window
window-title Render Pipeline by tobspr 


# Framebuffers use SRGB
framebuffer-srgb #f

# Framebuffers need no multisamples
framebuffer-multisample #f
multisample #f

# No V-Sync
sync-video #t


# Compress texture?
# driver-compress-textures #t


# Better performance for vertices??
# display-lists #t


# Faster animations??
# matrix-palette #t
# display-list-animation #t

# Don't rescale textures which are no power-of-2
textures-power-2 none


# Dump shaders
# gl-dump-compiled-shaders #f

# Better GL performance
gl-finish #f
gl-force-no-error #t
gl-force-no-flush #t
gl-force-no-scissor #t
gl-debug #t



