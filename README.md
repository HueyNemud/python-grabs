A simple python tool to grab archival documents from http://bibliotheques-specialisees.paris.fr

#### Installation (requires Python 3.6+)
`pip install --upgrade git+https://github.com/HueyNemud/python-grabs.git`

## CLI
```
Usage: grabs [OPTIONS]

Options:
  -s, --src TEXT            The URL of the document to retrieve.  [required]
  -o, --out-dir TEXT        Path to a directory where the documents data will
                            be stored. Default in the current folder.

  -z, --zoom-level INTEGER  The zoom level at which the images will be
                            downloaded. If not specified, the maximum zoom
                            level for each image will be used.

  -r, --recursive           Download the subviews of the document set with -s.
  -x, --no-images           If set, only the metadata of images will be
                            downloaded.

  -v, --verbose             Verbose mode.
  --help                    Show this message and exit.
```

**Examples:**
```bash
# Download a single image and save it to /tmp
grabs -s https://bibliotheques-specialisees.paris.fr/ark:/73873/pf0000935076/v0001 -o /tmp

# Download the metadata and images (on max resolution) of a document and save it to /tmp
grabs -s https://bibliotheques-specialisees.paris.fr/ark:/73873/pf0000935076 -o /tmp

# Grab only the metadata of a collection document all its child documents
grabs --no-images -r -s https://bibliotheques-specialisees.paris.fr/ark:/73873/pf0001950930 

# Download the images of all the images in a collection document at zoom-level 10
grabs -r -z 10 -s https://bibliotheques-specialisees.paris.fr/ark:/73873/pf0001950930 

```

## Python module
```python
import grabs

# A simple document : one page, 0 or more images attached
doc = grabs.document('https://bibliotheques-specialisees.paris.fr/ark:/73873/pf0000935076')
print(doc)

# Retrieve the first image at maximum zoom
first_image = doc.images[0]
imcontent = first_image.content()
imcontent.save(first_image.file_name)

# Retrieve the second image at zoom=11, this time asynchronously using a callback function
second_image = doc.images[1]

def callback(zoom, future):
    r = future.result()
    r.save(second_image.file_name)

second_image.content(zoom_level=11, callback=callback)

# A Collection document
doc = grabs.document('https://bibliotheques-specialisees.paris.fr/ark:/73873/pf0001950930')
print(doc)

if doc.is_collection():
    for subdoc in doc.children:
        print(subdoc)
```
