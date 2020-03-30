A simple python tool to grab archival documents from http://bibliotheques-specialisees.paris.fr

#### Installation (Requires Python 3.7+)
`pip install git+https://github.com/HueyNemud/python-grabs.git`

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
  -d, --no-download         If set, only the metadata of images will be
                            downloaded.

  -v, --verbose             Verbose mode.
  --help                    Show this message and exit.
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


first_image.content(zoom_level=11, callback=callback)

# A Collection document
doc = grabs.document('https://bibliotheques-specialisees.paris.fr/ark:/73873/pf0001950930')
print(doc)

if doc.is_collection():
    for subdoc in doc.subviews:
        print(subdoc)
```
