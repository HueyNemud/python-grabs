from . import resource


def document(url):
    return resource.DocumentBuilder(url).build()


def tiled_image(viewer_url = None, manifest_url = None, tiles_url = None):
    return resource.TiledImageBuilder(viewer_url, manifest_url, tiles_url).build()
