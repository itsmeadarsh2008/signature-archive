# Add signatures through an endless prompt (blank URL or Ctrl-C stops).
fill:
    @{{python}} fill.py

# Same endless prompt, but save the downloaded files untouched.
fill-raw:
    @{{python}} fill.py --raw

# Add one signature, processed to transparent white ink.
add url name:
    @{{python}} fill.py {{quote(url)}} {{quote(name)}}

# Add one signature without processing it.
add-raw url name:
    @{{python}} fill.py --raw {{quote(url)}} {{quote(name)}}

# Print the exact filename stem used for an artist's asset.
key name:
    @{{python}} fill.py --key {{quote(name)}}

# Show what is currently in the archive.
list:
    @ls -1 assets

# Create .venv and install Pillow (optional if Pillow is already available).
setup:
    @python3 -m venv .venv
    @.venv/bin/python -m pip install -r requirements.txt

python := if path_exists(".venv/bin/python") == "true" { ".venv/bin/python" } else { "python3" }
