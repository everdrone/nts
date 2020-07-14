import setuptools

setuptools.setup(
    name="nts-everdrone",
    version="1.1.4",
    author="Giorgio Tropiano",
    author_email="giorgiotropiano@gmail.com",
    description="NTS Radio downloader tool",
    long_description=open('readme.md').read(),
    long_description_content_type="text/markdown",
    url="https://github.com/everdrone/nts",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    license='MIT',
    scripts=['bin/nts'],
    install_requires=[
        'youtube_dl',
        'beautifulsoup4',
        'mutagen'
    ],
    python_requires='>=3.7.5',
)
