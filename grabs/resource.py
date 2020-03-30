import requests
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from dataclasses import (dataclass, field)
from .untiler import Untiler
import math
import traceback

BIBLIOTHEQUES_SPECIALISEES = 'bibliotheques-specialisees.paris.fr'
SCHEME = 'https'
DEFAULT_FORMAT = 'jpg'
COLLECTIONS_TYPE = ['CollectionIconography']


# Helper methods
def make_bs_url(parts):
    return urlparse(f'{SCHEME}://{BIBLIOTHEQUES_SPECIALISEES}/{parts}').geturl()


def get_js_var(source, varname):
    regex = f'var\s{varname}\\s+=\\s+["|\']*(.+?)["|\']*\\s*;'
    matches = re.search(regex, source)
    return matches.group(1) if matches else None


def fetch_html(url):
    r = requests.get(url)
    r.raise_for_status()
    return BeautifulSoup(r.text, features='html.parser')


# Content classes
@dataclass(frozen=True)
class Document:
    url: str
    ark: str
    iid: str
    category: str
    parent_iid: str
    properties: field(default_factory=dict)
    properties_lang: str
    images: field(default_factory=tuple)
    children_urls: field(default_factory=tuple)
    where_to_find_it: str = ''

    def get_prop(self, prop_name = ''):
        prop = self.properties.get(prop_name)
        if prop:
            return prop['name'], prop['values'], self.properties_lang

    @property
    def children(self):
        for children in self.children_urls:
            yield DocumentBuilder(children).build()

    def is_collection(self):
        return self.category in COLLECTIONS_TYPE or len(self.children_urls)


@dataclass(frozen=True)
class TiledImage:
    iid: str
    ark: str # TODO : replace with gallipy ARK objects
    manifest_url: str
    tiles_url: str
    viewer_url: str = None
    title: str = None
    file_name: str = None
    description: str= None
    parent_url: str = None
    format: str = DEFAULT_FORMAT
    width: int = 0
    height: int = 0
    tile_size: int = 0
    overlap: int = 0
    __cache: dict = field(default_factory=dict, repr=False, init=False) # TODO : cache on disk instead of in memory

    @property
    def max_zoom(self):
        max_n = max(self.width, self.height) / self.tile_size
        max_zoom = math.floor(math.log2(max_n)) # Dark
        return 10 + max_zoom # The base zoom is 10

    def content(self, zoom_level=None, callback=None, caching=True):

        zoom_level = zoom_level or self.max_zoom
        cached = self.__cache.get(zoom_level) if caching else None

        if cached:
            return cached

        callbacks = [callback] if callback else []
        if caching:
            callbacks.append(self.__cache_callback)

        future = Untiler().untile(self, zoom_level, callbacks=callbacks)

        return future.result() if not callback else future

    def __cache_callback(self, zoom_level, data):
        self.__cache[zoom_level] = data.result() # dicts are thread safe


# Builders
class TiledImageBuilder:

    # A tile image can be constructed from the url of either the manifest or the viewer of that image.
    # The remote location of the tiles can be set with tiles_url.
    # If tiles_urls is not set, the location of the tiles will be deduced from the manifest url.
    def __init__(self, viewer_url=None, manifest_url=None, tiles_url=None):
        if not (viewer_url or manifest_url):
            raise ValueError("At least one of viewer_url or manifest_url must be passed to the constructor.")
        self.manifest_url = urlparse(manifest_url).geturl() if manifest_url else None
        self.viewer_url = urlparse(viewer_url).geturl() if viewer_url else None
        self.tiles_url = urlparse(tiles_url).geturl() if tiles_url else None

    def build(self):

        image_metadata = { 'iid': '', 'ark': ''}

        # We use the viewer to retrieve most of the image metadata
        if self.viewer_url:
            image_metadata['viewer_url'] = self.viewer_url
            source = fetch_html(self.viewer_url).text
            image_metadata['iid'] = get_js_var(source, 'iid')
            image_metadata['ark'] = get_js_var(source, 'ark')

            ark_parts = re.search(r'(.+)/v(\d+)', image_metadata['ark']) # TODO : use Gallipy
            image_number = int(ark_parts.group(2))
            parent_ark = ark_parts.group(1)
            parent_url = make_bs_url(parent_ark)

            picture_list = get_js_var(source, 'pictureList')
            pictures = json.loads(picture_list)
            mdata = pictures[image_number-1]

            if not self.manifest_url:
                self.manifest_url = make_bs_url(mdata["deepZoomManifest"])

            image_metadata['manifest_url'] = self.manifest_url
            image_metadata['title'] = mdata["pagination"]
            image_metadata['description'] = mdata["description"]

        manifest_data = self.__fetch_manifest()
        image_metadata.update(manifest_data)

        if not manifest_data:
            raise ValueError(f'No metadata could be retrieved from manifest {self.manifest_url}')

        # Retrieve the image name
        matches = re.search(r'.+/(.+?)\.xml', self.manifest_url)
        if matches:
            file_name = matches.group(1)
            image_metadata['file_name'] = f'{file_name}.{image_metadata["format"]}'

        if not self.tiles_url:
            # tiles_url will be guessed from the manifest url.
            path = re.search(r'(.+)\.xml',self.manifest_url).group(1)
            self.tiles_url = path

        image_metadata['manifest_url'] = self.manifest_url
        image_metadata['tiles_url'] = self.tiles_url
        return TiledImage(**image_metadata)

    def __fetch_manifest(self):
        query = f'/in/rest/pictureListSVC/getTileSource?deepZoomManifest={self.manifest_url}'
        url = make_bs_url(query)
        r = requests.get(url)
        r.raise_for_status()
        json_txt = r.text[1:-1].replace('\\','')
        data = json.loads(json_txt).get("Image")
        try:
            return {
                'format': data['Format'],
                'width': data['Size']['Width'],
                'height': data['Size']['Height'],
                'overlap': data['Overlap'],
                'tile_size': data['TileSize'],
            }
        except TypeError as te:
            traceback.print_exc()
            raise ValueError(f"Cannot fetch image metadata from manifest <{self.manifest_url}>. Fetched {data}.")


class DocumentBuilder:

    def __init__(self, url):
        self.document_url = urlparse(url).geturl()
        self.source = fetch_html(self.document_url)

    def build(self):
        document_metadata = {}
        source_txt = self.source.text
        document_metadata['url'] = self.document_url
        document_metadata['ark'] = self.__get_ark()
        document_metadata['category'] = get_js_var(source_txt, 'zmat')
        document_metadata['iid'] = get_js_var(source_txt, 'instanceiid')
        document_metadata['parent_iid'] = get_js_var(source_txt, 'parent_iid')
        document_metadata['properties'] = self.__get_props()
        document_metadata['properties_lang'] = get_js_var(source_txt, 'currLocale')
        document_metadata['where_to_find_it'] = 'Not yet implemented' # TODO Not yet implemented in the builder
        images = []

        picture_list = get_js_var(source_txt, 'pictureList')  # Is there any image attached to this document ?
        if picture_list:
            links = json.loads(picture_list)
            for idx, link in enumerate(links):
                manifest = make_bs_url(link['deepZoomManifest'])
                view = f'{document_metadata["ark"]}/v{str(idx).zfill(4)}'
                view_url = make_bs_url(view)
                image = TiledImageBuilder(view_url, manifest_url=manifest).build()
                images.append(image)
        document_metadata['images'] = images

        children_urls = DocumentBuilder.__get_links_to_childrens(document_metadata['iid'])
        document_metadata['children_urls'] = children_urls

        return Document(**document_metadata)

    def __get_ark(self):
        m = re.search(r'ark:\/[^\?]+\/[^\?]+', self.document_url)
        if m:
            return m.group(0)

    @staticmethod
    def __get_links_to_childrens(document_id):
        f_name = 'InterviewId'
        # the childrens are added dynamically so we can't get them directly from the page source
        query = f'https://bibliotheques-specialisees.paris.fr/in/rest/searchSVC/jsonp/geoquery?callback=&query=*&fq=parent_iid:"{document_id}"&fl={f_name}'
        r = requests.get(query)
        r.raise_for_status()
        json_str = r.text[1:-4] # r returns a javascript call "(json);" but we only want the json
        results = json.loads(json_str).get("results")
        sub_arks = [result.get(f_name).get("value") for result in results]
        return [make_bs_url(ark) for ark in sub_arks]

    def __get_props(self):
        prop_containers = self.source.findAll("div", {"class":"NormalField"})
        props = {}
        for container in prop_containers:
            prop = [cls for cls in container['class'] if 'property' in cls][0]
            prop = prop.replace('property_','') # remove the prefix
            children = container.findAll("div", recursive=False)
            propname = children[0].find("span").text.strip()
            propvalue = children[1].find("div").text.strip()
            propentry = props.get(prop)
            if propentry:
                if not propentry.get('name') and propname:
                    propentry['name'] = propname
                propentry.get('values').append(propvalue)
            else:
                props[prop] = {'name': propname,
                               'values': [propvalue]}
        return props