from pelican import signals
import grits
from pathlib import Path
import tempfile
import os
import shutil

DEBUG = True


def clean_directory(directory):
    for file_object in os.listdir(directory):
        file_object_path = os.path.join(directory, file_object)
        if os.path.isfile(file_object_path):
            os.unlink(file_object_path)
        else:
            shutil.rmtree(file_object_path)


def copy_contents(src, dst):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks=False, ignore=None)
        else:
            shutil.copy2(s, d)


def post_process(pelican):
    src_dir = pelican.settings["OUTPUT_PATH"]
    if DEBUG:
        tmp_dir = Path(src_dir).parent / "_output_grits"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        out_dir = str(tmp_dir)
    else:
        tmp_dir = tempfile.TemporaryDirectory(prefix="grits-tmp")
        out_dir = tmp_dir.name

    renderer = grits.build(
        src_dir=src_dir,
        out_dir=out_dir,
        template_dir="theme/templates"
    )
    renderer.render_template("static/style.min.css")

    # Nuke the intermediate output
    clean_directory(src_dir)
    copy_contents(out_dir, src_dir)


def register():
    signals.finalized.connect(post_process)
