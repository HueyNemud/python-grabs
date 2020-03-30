import requests
import warnings
import math
import concurrent.futures as cf
from PIL import (Image, ImageDraw)
from io import BytesIO
from . import resource
from dataclasses import (dataclass)

MODES_FORMATS = {'jpg': 'RGB', 'jpeg': 'RGB', 'png': 'RGBA'}


@dataclass(frozen=True)
class _UntileQuery:
    # Forward reference to the type to avoid type hints errors cause by
    # the circular dependency between _UntileQuery and TiledImage
    image: 'resource.TiledImage'
    zoom_level: int

    def __post_init__(self):
        mz = self.image.max_zoom
        zl = self.zoom_level
        if zl > mz:
            raise ValueError(f"Zoom level ({zl}) is greater than the maximum possible zoom ({mz}) for {self.image.file_name}.")

    def width(self):
        return int(self.image.width / 2 ** (self.image.max_zoom - self.zoom_level))

    def height(self):
        return int(self.image.height / 2 ** (self.image.max_zoom - self.zoom_level))

    def tiles_urls(self):
        zl_width = self.width()
        zl_height = self.height()

        if max(zl_width, zl_height) < 1:
            warnings.warn(f'Image at zoom level {self.zoom_level} is smaller than 1 pixel.')

        n_columns = math.ceil(zl_width / self.image.tile_size)
        n_rows = math.ceil(zl_height / self.image.tile_size)

        def url_template(root, zl, col, row, frmt):
            return f'{root}/{zl}/{col}_{row}.{frmt}'

        tile_matrix = {}
        for col_idx in list(range(0, n_columns)):
            for row_idx in list(range(0, n_rows)):
                tile_matrix[col_idx, row_idx] = url_template(self.image.tiles_url, self.zoom_level, col_idx, row_idx, self.image.format)
        return tile_matrix

    @staticmethod
    def fetch_tile(index, tile_url):
        r = requests.get(tile_url)
        r.raise_for_status()
        return index + (r.content,)


class Untiler:

    DRAW_TILES_BOUNDS = False

    @staticmethod
    def untile(image, zoom_level, callbacks):
        query = _UntileQuery(image,zoom_level)

        def propagate(fut):
            for cb in callbacks:
                cb(zoom_level, fut)

        with cf.ThreadPoolExecutor(1) as executor:
            future = executor.submit(Untiler.__build_image, query)
            if callbacks:
                future.add_done_callback(propagate)
            return future

    @staticmethod
    def __build_image(query: _UntileQuery):
        tiles_urls = query.tiles_urls()
        tile_matrix = {}

        tiles = [query.fetch_tile(idx, url) for idx, url in tiles_urls.items()]
        for tile in tiles:
            tile_matrix[tile[0], tile[1]] = Image.open(BytesIO(tile[2]))

        dims = (query.width(), query.height())
        untiled = Image.new(MODES_FORMATS[query.image.format],dims)

        t_size = query.image.tile_size
        overlap = query.image.overlap
        for index, tile in tile_matrix.items():
            # FIX: Tiles of the firt column (resp. first row) seem to have
            # no overlapping area on the left (resp. top) border.
            overlap_x = query.image.overlap if index[0] else 0
            overlap_y = query.image.overlap if index[1] else 0
            crop_rectangle = (overlap_x,
                              overlap_y,
                              t_size + overlap_x,
                              t_size + overlap_y)
            non_overlapping = tile.crop(crop_rectangle)
            cursor = (index[0] * t_size, index[1] * t_size)
            untiled.paste(non_overlapping, box=cursor)

        # paint the grid on top of the image
        if Untiler.DRAW_TILES_BOUNDS:
            draw = ImageDraw.Draw(untiled)
            for index, tile in tile_matrix.items():
                cursor = (index[0] * t_size, index[1] * t_size)
                # Draw boundaries with overlapping
                tile_bbox = [cursor[0] - overlap, cursor[1] - overlap * 2, cursor[0] + tile.width - overlap,
                             cursor[1] + tile.height - overlap * 2]
                draw.rectangle(tile_bbox, outline='cyan')

        return untiled