import numpy


def polar2cart(r, theta, center):
    x = r * numpy.cos(theta) + center[0]
    y = r * numpy.sin(theta) + center[1]
    return x, y


def compute_image_xy_cart(im, center=None, phase_width=3000,
                          initial_radius=0, final_radius=None):
    if center is None:
        center = (im.shape[1] / 2, im.shape[0] / 2)
    if final_radius is None:
        final_radius = min(center[0], center[1])
    return compute_xy_cart(initial_radius, final_radius, phase_width, center)


def compute_xy_cart(initial_radius, final_radius, phase_width, center):
    theta, R = numpy.meshgrid(x=numpy.linspace(0, 2*numpy.pi, phase_width),
                              y=numpy.arange(initial_radius, final_radius))
    return polar2cart(R, theta, center)


def img2polar(img, center=None, final_radius=None, initial_radius=0,
              phase_width=3000, xy_cart=None):
    if center is None:
        center = (img.shape[1] / 2, img.shape[0] / 2)
    if final_radius is None:
        final_radius = min(center[0], center[1])
    if xy_cart is None:
        Xcart, Ycart = compute_xy_cart(
            initial_radius, final_radius, phase_width, center)
    else:
        Xcart, Ycart = xy_cart

    Xcart = Xcart.astype(int)
    Ycart = Ycart.astype(int)

    if img.ndim == 3:
        polar_img = img[Ycart, Xcart, :]
        polar_img = numpy.reshape(
            polar_img, (final_radius - initial_radius, phase_width, 3))
    else:
        polar_img = img[Ycart, Xcart]
        polar_img = numpy.reshape(
            polar_img, (final_radius - initial_radius, phase_width))

    return polar_img
