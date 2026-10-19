"""Include the existing built Web App in release distributions."""

from pathlib import Path
from shutil import copytree

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithWebApp(build_py):
    def run(self):
        super().run()
        frontend = Path(__file__).parent / "web/dist"
        if (frontend / "index.html").is_file():
            copytree(
                frontend, Path(self.build_lib) / "math_research/app/static", dirs_exist_ok=True
            )


setup(cmdclass={"build_py": BuildWithWebApp})
