import os
import shutil

import PyInstaller.__main__

# NOTE: To package this correctly with PyInstaller, a source code file belonging to the package 'alive_progress' has to be modified:
#
# File: alive-progress/alive_progress/core/configuration.py
# In the function '__func_lookup', the condition 'os.path.splitext(x.__code__.co_filename)[0] == func_file' must be removed
#
# This is easily done in a VENV

PyInstaller.__main__.run([
    '--name=%s' % "AstroTuxLauncher",
    '--onefile',
    '--noupx',
    '--collect-all', 'grapheme',
    '--collect-all', 'about-time',
    'AstroTuxLauncher.py'
])

shutil.rmtree("build")
os.remove("AstroTuxLauncher.spec")