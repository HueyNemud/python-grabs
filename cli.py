import click
import grabs
import re
import dataclasses, json
from pathlib import Path
import logging as log


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


@click.command()
@click.option("--src", "-s", required=True,
              help="The URL of the document to retrieve.",
)
@click.option("--out-dir", "-o", default=".",
              help="Path to a directory where the documents data will be stored. Default in the current folder.")
@click.option("--zoom-level", "-z", default=10,
              help="The zoom level at which the images will be downloaded. If not specified, the maximum zoom level for each image will be used.")
@click.option("--recursive", "-r", is_flag=True, default=False,
              help="Download the subviews of the document set with -s.")
@click.option("--no-download", "-d", is_flag=True, default=False,
              help="If set, only the metadata of images will be downloaded.")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Verbose mode.")
def grab(src, out_dir, recursive=False, zoom_level=10, no_download=False, verbose=False):
    if verbose:
        log.basicConfig(format="%(message)s", level=log.INFO)
        log.info("Verbose output.")

    path_out = Path(out_dir)
    path_out.mkdir(parents=True, exist_ok=True)

    # URL contains an ark finishing with something like v0008 ? That's an image. Otherwise consider it to be a document
    regex = re.compile('ark:.+/v\d+')

    pool = []

    if regex.search(src):
        im = grabs.tiled_image(src)
        log.info(f'Found tiled image {im}')
        serialized = serialize_json(im)
        pool.append((im, serialized))
    else:
        doc = grabs.document(src)
        log.info(f'Found document {doc} with {len(doc.subviews_urls)} subviews and {len(doc.images)}')
        serialized = serialize_json(doc)
        pool.append((doc, serialized))
        if recursive:
            for sub in doc.subviews:
                log.info(f'Found subview {sub}')
                serialized = serialize_json(sub)
                pool.append((sub, serialized))

    # Write the metadata files
    for element, mdata in pool:
        md_file_name = element.ark or src
        path = make_path(path_out,md_file_name)
        log.info(f'Writing element {element} to {path}')
        with open(path, 'w') as md_file:
            md_file.write(serialized)

    # Download the images if asked to
    if not no_download:
        images = []
        for element, _ in pool:
            if isinstance(element, grabs.resource.TiledImage):
                get_save_image(path_out,im, zoom_level)
            elif isinstance(element, grabs.resource.Document):
                for im in element.images:
                    get_save_image(path_out, im, zoom_level)

    print(f'Saved {len(pool)} document{"s" if len(pool) != 1 else ""} to {Path(out_dir)}')


if __name__ == '__main__':
    grab()