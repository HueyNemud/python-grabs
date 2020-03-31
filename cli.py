import click
import grabs
import re
import dataclasses, json
import logging
import concurrent.futures as cf
from pathlib import Path

logging.basicConfig(format="%(message)s") # Root logger
log = logging.getLogger('cli') # Local logger

MAX_WORKERS = 5
FETCH_TIMEOUT = 20


def make_path(directory, file_name):
    return f'{directory}/{file_name.replace("/", "_")}'


def serialize_json(dataclass_instance):
    return json.dumps(dataclasses.asdict(dataclass_instance), indent=2, sort_keys=True, ensure_ascii=False)


def get_save_image(path_out, im, zoom_level):
    log.info(f'Grabbing image {im.file_name} [zoom level = {zoom_level}]')
    imdata, success_rate = im.content(zoom_level)
    im_file_name = im.file_name
    path = make_path(path_out, im_file_name)

    if success_rate < 1:
        log.warning(f'\033[1mParts of the untiled image {im.file_name} are missing.' \
                    f'You could try again by calling grabs with the image\'s url {im.viewer_url}\033[0m')

    imdata.save(path)
    log.debug(f'Image {im.id} saved to {path}')


def print_end_message(out_dir, n_docs, n_img=0, success_img=0):
    msg = f'Saved {n_docs} document{"s" if n_docs != 1 else ""} metadata'
    if n_img:
        msg += f' and {success_img}/{n_img} image{"s" if n_img != 1 else ""} to {Path(out_dir)}'
    log.info(msg)

@click.command()
@click.option("--src", "-s", required=True,
              help="The URL of the document to retrieve.",
)
@click.option("--out-dir", "-o", default=".",
              help="Path to a directory where the documents data will be stored. Default in the current folder.")
@click.option("--zoom-level", "-z", default=None, type=int,
              help="The zoom level at which the images will be downloaded. "
              + "If not specified, the maximum zoom level for each image will be used. "
              + "The minimum zoom level is usually 10.")
@click.option("--recursive", "-r", is_flag=True, default=False,
              help="Download the sub-documents of the document set with -s.")
@click.option("--no-images", "-x", is_flag=True, default=False,
              help="If set, only the metadata of images will be downloaded.")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Verbose mode.")
def grab(src, out_dir, recursive=False, zoom_level=None, no_images=False, verbose=False):
    log_level = logging.DEBUG if verbose else logging.INFO
    log.setLevel(log_level)

    path_out = Path(out_dir)
    path_out.mkdir(parents=True, exist_ok=True)

    # URL contains an ark finishing with something like v0008 ? That's an image. Otherwise consider it to be a document
    regex = re.compile('ark:.+/v\d+')

    pool = []

    if regex.search(src):
        im = grabs.tiled_image(src)
        log.info(f'Found tiled image at {im.viewer_url}')
        log.debug(f'Detail: {im}')
        serialized = serialize_json(im)
        pool.append((im, serialized))
    else:
        doc = grabs.document(src)
        log.info(f'Found document at {doc.url} with {len(doc.children_urls)} children documents')
        serialized = serialize_json(doc)
        pool.append((doc, serialized))
        if recursive:
            for sub in doc.children:
                log.debug(f'Found child document {sub.url} with {len(sub.images)} images')
                serialized = serialize_json(sub)
                pool.append((sub, serialized))

    n_img =0
    n_img_failed = 0
    # Grab documents and attached images
    for idx, e in enumerate(pool):
        element, mdata = e
        log.info(f'Grabbing document {element.id} ({idx+1}/{len(pool)})')

        md_file_name = element.ark or src
        path = make_path(path_out, md_file_name)
        with open(path, 'w') as md_file:
            md_file.write(serialized)
            log.debug(f'Metadata saved to {path}')

        if not no_images:
            if isinstance(element, grabs.resource.TiledImage):
                images = [element]
            elif isinstance(element, grabs.resource.Document):
                images = element.images
            log.debug(f'Found {len(images)} image(s) to download')
            n_img += len(images)
            with cf.ThreadPoolExecutor(MAX_WORKERS) as executor:
                futures = [executor.submit(get_save_image, path_out, im, zoom_level or im.max_zoom) for im in images]
                finished, unfinished = cf.wait(futures, timeout=FETCH_TIMEOUT, return_when=cf.ALL_COMPLETED)
                for unf in unfinished:
                    try:
                        unf.result()
                    except ValueError as e:
                        log.error(f'ERROR: The download of an image failed. Caused by: \n {e}')
                        n_img_failed += 1
    print_end_message(out_dir, len(pool), n_img, n_img - n_img_failed)


if __name__ == '__main__':
    grab()