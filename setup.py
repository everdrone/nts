import setuptools

with open('requirements.txt') as f:
    requirements = f.readlines()

with open("readme.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="nts-everdrone",
    version="1.0.0",
    author="Giorgio Tropiano",
    author_email="giorgiotropiano@gmail.com",
    description="NTS Radio downloader tool",
    long_description=long_description,
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
    install_requires=requirements,
    python_requires='>=3.7.5',
)
