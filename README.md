# Personal News Dashboard

This project is a static site generator for a personal news dashboard. It fetches data from various RSS feeds and builds a static HTML site that can be hosted on any web server.

## Runtime

The project is built using Python and the dependencies are managed with `uv`. The dependencies are listed in the `pyproject.toml` file.

The static site is built by running the `build.py` script. This script fetches the latest content from the RSS feeds, generates the HTML pages, and places them in the `docs` directory.

## Accessing the Results

The generated static site is located in the `docs` directory. You can open the `index.html` file in your web browser to view the site locally.

This project is configured to be automatically built and deployed to GitHub Pages. The site is updated every 30 minutes. You can access the live site at `https://<your-github-username>.github.io/<your-repository-name>/`.

The dashboard includes content from the following sources:

*   Hacker News
*   Reddit
*   proggit
*   dzone
*   Slashdot
*   Techmeme
*   Wired
*   YouTube (videos from various subreddits)
