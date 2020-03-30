import requests
import warnings
import math
import concurrent.futures as cf
from PIL import (Image, ImageDraw)
from io import BytesIO
from . import resource
from dataclasses import (dataclass)

MAX_WORKERS = 10
FETCH_TIMEOUT = 20
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
            raise ValueError(f"Zoom level ({zl})is greater than the maximum possible zoom ({mz}) for this image.")

    def width(self):
        return int(self.image.width / 2 ** (self.image.max_zoom - self.zoom_level))

    def height(self):
        return int(self.image.height / 2 ** (self.image.max_zoom - self.zoom_level))

    def tiles_urls(self):
        zl_width = self.width()
        zl_height = self.height()

        if zl_width < 1 or zl_height < 1:
            warnings.warn(f'Tiles at zoom level {self.zoom_level} are smaller than 1 pixel.')

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

    def __init__(self, max_workers = MAX_WORKERS, fetch_timeout = FETCH_TIMEOUT):
        self.max_workers = max_workers
        self.fetch_timeout = fetch_timeout

    def untile(self, image, zoom_level, callbacks):
        query = _UntileQuery(image,zoom_level)

        def propagate(future):
            for cb in callbacks:
                cb(zoom_level, future)

        with cf.ThreadPoolExecutor(1) as executor:
            future = executor.submit(self.__exec_multithread, query)
            if callbacks:
                future.add_done_callback(propagate)
            return future

    def __exec_multithread(self, query: _UntileQuery):
        tiles_urls = query.tiles_urls()
        tile_matrix = {}

        with cf.ThreadPoolExecutor(self.max_workers) as executor:
            futures = [executor.submit(query.fetch_tile, idx, url) for idx, url in tiles_urls.items()]
            cf.wait(futures, timeout=self.fetch_timeout, return_when=cf.FIRST_EXCEPTION)

            for future in futures:
                tile = future.result()
                tile_matrix[tile[0], tile[1]] = Image.open(BytesIO(tile[2]))

            dims = (query.width(), query.height())

            untiled = Image.new(MODES_FORMATS[query.image.format],dims) # TODO Mode should depends on the format

            max_rows_idx = max([idx[1] for idx in tile_matrix.keys()])
            cursor = (0, 0)
            for index, tile in tile_matrix.items():
                w = tile.width
                h = tile.height
                untiled.paste(tile, cursor)
                y_offset = cursor[1] + h - query.image.overlap if index[1] < max_rows_idx else 0
                x_offset = cursor[0] + w - query.image.overlap if index[1] == max_rows_idx else cursor[0]
                cursor = (x_offset, y_offset)

            # Run separately because of overlap
            if Untiler.DRAW_TILES_BOUNDS:
                draw = ImageDraw.Draw(untiled)
                cursor = (0, 0)
                for index, tile in tile_matrix.items():
                    w = tile.width
                    h = tile.height
                    draw.rectangle([cursor, (cursor[0] + w, cursor[1] + h)],outline='red')
                    y_offset = cursor[1] + h - query.image.overlap if index[1] < max_rows_idx else 0
                    x_offset = cursor[0] + w - query.image.overlap if index[1] == max_rows_idx else cursor[0]
                    cursor = (x_offset, y_offset)

            return untiled