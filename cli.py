import click
import grabs
import re
import dataclasses, json
import logging as log
import concurrent.futures as cf
from pathlib import Path

MAX_WORKERS = 5
FETCH_TIMEOUT = 50

log.basicConfig(format="%(message)s", level=log.INFO)

def make_path(directory, file_name):
    return f'{directory}/{file_name.replace("/", "_")}'


def serialize_json(dataclass_instance):
    return json.dumps(dataclasses.asdict(dataclass_instance), indent=2, sort_keys=True, ensure_ascii=False)


def get_save_image(path_out, im, zoom_level):
    log.info(f'Fetching image {im.file_name} [Zoom level = {zoom_level}]')
    imdata = im.content(zoom_level)
    im_file_name = im.file_name
    path = make_path(path_out, im_file_name)
    log.info(f'Saving to {path}')
    imdata.save(path)


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
              help="The zoom level at which the images will be downloaded. If not specified, the maximum zoom level for each image will be used.")
@click.option("--recursive", "-r", is_flag=True, default=False,
              help="Download the sub-documents of the document set with -s.")
@click.option("--no-images", "-x", is_flag=True, default=False,
              help="If set, only the metadata of images will be downloaded.")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Verbose mode.")
def grab(src, out_dir, recursive=False, zoom_level=None, no_images=False, verbose=False):
    if verbose:
        log.basicConfig(format="%(message)s", level=log.DEBUG)
        log.info("Verbose output.")

    path_out = Path(out_dir)
    path_out.mkdir(parents=True, exist_ok=True)

    # URL contains an ark finishing with something like v0008 ? That's an image. Otherwise consider it to be a document
    regex = re.compile('ark:.+/v\d+')

    pool = []

    if regex.search(src):
        im = grabs.tiled_image(src)
        log.info(f'Found tiled image at {im.viewer_url}')
        log.debug(im)
        serialized = serialize_json(im)
        pool.append((im, serialized))
    else:
        doc = grabs.document(src)
        log.info(f'Found document at {doc.url} with {len(doc.children_urls)} subviews and {len(doc.images)} images')
        log.debug(doc)
        serialized = serialize_json(doc)
        pool.append((doc, serialized))
        if recursive:
            for sub in doc.children:
                log.info(f'Found child document {sub.url} with {len(sub.images)} images')
                log.debug(sub)
                serialized = serialize_json(sub)
                pool.append((sub, serialized))

    # Write the metadata files
    for element, mdata in pool:
        md_file_name = element.ark or src
        path = make_path(path_out,md_file_name)
        log.info(f'Saving metadata to {path}')
        with open(path, 'w') as md_file:
            md_file.write(serialized)
        log.debug(serialized)

    # Download the images if asked to
    n_img = 0
    n_img_success = 0
    if not no_images:
        for element, _ in pool:
            if isinstance(element, grabs.resource.TiledImage):
                images = [element]
            elif isinstance(element, grabs.resource.Document):
                images = element.images

            n_img += len(images)
            with cf.ThreadPoolExecutor(MAX_WORKERS) as executor:
                futures = []
                for im in images:
                    zl = zoom_level or im.max_zoom
                    futures.append(executor.submit(get_save_image, path_out, im, zl))
                n_img_success += len(images)
                finished, unfinished = cf.wait(futures, timeout=FETCH_TIMEOUT, return_when=cf.FIRST_EXCEPTION)
                for f in unfinished:
                    try:
                        f.result()
                    except ValueError as e:
                        n_img_success -= 1
                        log.error("ERROR: An image could not be downloaded. Caused by:")
                        print(e)
        print_end_message(out_dir, len(pool), n_img, n_img_success)
    else:
        print_end_message(out_dir, len(pool))


if __name__ == '__main__':
    grab()