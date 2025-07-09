import setuptools

setuptools.setup(
    name="nts-everdrone",
    version="1.3.7",
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
    entry_points={'console_scripts': ['nts=nts.cli:main']},
    install_requires=[
        'yt-dlp==2024.7.25',
        'beautifulsoup4==4.9.3',
        'mutagen==1.45.1',
        'requests==2.32.2',
        'cssutils==2.7.1',
        'ffmpeg-python==0.2.0',
        'music-tag==0.4.3',
        'pillow==10.4.0',
    ],
    python_requires='>=3.7.5',
)
