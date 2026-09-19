#!/usr/bin/env python3
"""
Export Kobo markups (drawings) as composed images (PNG).

Each markup is stored as {BookmarkID}.svg (vector strokes, transparent
background) plus {BookmarkID}.jpg (the page without the drawing). This
module renders the SVG over the JPG and embeds the resulting image in the
Markdown export. Really cool, right?
"""

import os
import shutil
import subprocess
import tempfile

from PIL import Image

# This is some module-level state shared by every export_markup() call.
# The underscore prefix marks these as internal to this module
_renderer = None
_cairo_warning_shown = False
_stats = {'composed': 0, 'skipped': 0, 'missing': 0}


def warn_missing_cairo():
    """Print the missing-CairoSVG warning only once."""
    global _cairo_warning_shown
    if not _cairo_warning_shown:
        print('WARNING: CairoSVG is not available. Markups will be skipped.'
              'Install it with "pip install cairosvg".')
        _cairo_warning_shown = True


def select_renderer():
    """Detect the available CairoSVG backend (Python module or CLI)."""
    global _renderer
    if _renderer is not None:
        return _renderer
    try:
        import cairosvg
        _renderer = 'cairosvg'
    except Exception:
        _renderer = 'cairosvg_cli' if shutil.which('cairosvg') else None

    if _renderer is None:
        warn_missing_cairo()
    return _renderer


def _render_svg(svg_path, png_path):
    renderer = select_renderer()
    if renderer == 'cairosvg':
        import cairosvg
        cairosvg.svg2png(url=svg_path, write_to=png_path)
        return True
    if renderer == 'cairosvg_cli':
        result = subprocess.run(['cairosvg', '-o', png_path, svg_path],
                                capture_output=True)
        return result.returncode == 0
    return False


def compose_markup(svg_path, jpg_path, png_path):
    """Render the drawing (SVG) over the page (JPG) into png_path."""
    if select_renderer() is None:
        return False
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as handle:
            temp_file = handle.name
        if not _render_svg(svg_path, temp_file):
            return False
        page = Image.open(jpg_path).convert('RGBA')
        strokes = Image.open(temp_file).convert('RGBA')
        if strokes.size != page.size:
            strokes = strokes.resize(page.size)
        Image.alpha_composite(page, strokes).convert('RGB').save(png_path, 'PNG')
        return True
    except Exception as error:
        print(f'Error composing markup {os.path.basename(svg_path)}: {error}')
        return False
    finally:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)


def _is_fresh(sources, destination):
    """True if destination exists and is newer than or equal to sources."""
    if not os.path.exists(destination):
        return False
    destination_mtime = os.path.getmtime(destination)
    return all(os.path.getmtime(source) <= destination_mtime
               for source in sources)


def bump(key):
    _stats[key] = _stats.get(key, 0) + 1


def summary():
    composed = _stats['composed']
    skipped = _stats['skipped']
    missing = _stats['missing']
    print(f'Markups: {composed} composed, '
          f'{skipped} already up to date, '
          f'{missing} missing source files.')


def export_markup(file, bookmark, output, config):
    """Write the markup into the Markdown file and compose its image."""
    markup_id = bookmark.BookmarkID
    markups_dir = config['markups_dir']
    svg_path = os.path.join(markups_dir, f'{markup_id}.svg')
    jpg_path = os.path.join(markups_dir, f'{markup_id}.jpg')
    if not (os.path.exists(svg_path) and os.path.exists(jpg_path)):
        print(f'WARNING: missing source files for markup {markup_id}')
        bump('missing')
        return

    destination_dir = os.path.join(output, config['attachments_dir'], 'markups')
    os.makedirs(destination_dir, exist_ok=True)
    png_path = os.path.join(destination_dir, f'{markup_id}.png')
    relative_path = f'{config["attachments_dir"]}/markups/{markup_id}.png'

    if _is_fresh((svg_path, jpg_path), png_path):
        bump('skipped')
    elif not compose_markup(svg_path, jpg_path, png_path):
        return  # renderer missing or composition failed
    else:
        bump('composed')

    file.write(f'{config["markup_callout"]}\n')
    file.write(f'> ![Markup]({relative_path})\n\n')
    file.write(f'**Location**: {chapter_location(bookmark)}\n')
    file.write(f'**Date**: {bookmark.DateModified}\n')
    file.write('\n---\n')


def chapter_location(bookmark):
    content = bookmark.ContentID or ''
    chapter = content.split('!')[-1] if '!' in content else ''
    location = bookmark.Location or ''
    return f'{location} · {chapter}' if chapter else location
