import os
from setuptools import setup, find_packages
from setuptools import setup


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name='grabs',
    version='0.1',
    description='Grab documents and images from http://bibliotheques-specialisees.paris.fr',
    long_description=read('README.md'),
    packages=find_packages(),
    license= "WTFPL",
    install_requires=[
        'Click',
        'requests',
        'bs4',
        'Pillow'
    ],
    classifiers=[],
    entry_points='''
        [console_scripts]
        grabs=cli:grab
    ''',
)
