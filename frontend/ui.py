# -*- coding: utf-8 -*-

from io import BytesIO
from json import dumps
from os import environ
from os.path import isfile, join
from re import fullmatch
from typing import Any

from flask import Blueprint, Response, redirect, render_template, request, send_file

from backend.base.files import folder_path
from backend.internals.server import Server

ui = Blueprint('ui', __name__)
methods = ['GET']
ALLOWED_THEMES = ["", "dark-mode"]


def render(filename: str, **kwargs: Any) -> str:
    theme = ''
    if "theme" in request.cookies and request.cookies["theme"] in ALLOWED_THEMES:
        theme = request.cookies["theme"]

    return render_template(
        filename,
        url_base=Server.url_base,
        theme=theme,
        **kwargs
    )


@ui.route('/manifest.json', methods=methods)
def ui_manifest():
    return send_file(
        BytesIO(dumps(
            {
                "name": "Kapowarr",
                "short_name": "Kapowarr",
                "description": "Kapowarr is a software to build and manage a comic book library, fitting in the *arr suite of software.",
                "display": "standalone",
                "orientation": "portrait-primary",
                "start_url": f"{Server.url_base}/",
                "scope": f"{Server.url_base}/",
                "id": f"{Server.url_base}/",
                "background_color": "#464b51",
                "theme_color": "#ebc700",
                "icons": [
                    {
                        "src": f"{Server.url_base}/static/img/favicon.svg",
                        "type": "image/svg+xml",
                        "sizes": "any"
                    }
                ]
            },
            indent=4
        ).encode('utf-8')),
        mimetype="application/manifest+json",
        download_name="manifest.json"
    ), 200


# Artwork for the visual themes. Drop your own files into
# <art dir>/<theme>/<character>.(webp|jpg|png) and they replace the
# placeholder with no code change. KAPOWARR_ART_DIR moves the folder.
ART_ACCENT = {
    "marvel": "#d81f26", "dragonball": "#f77f00", "crossover": "#7a3cff",
    "justice": "#0b2a6b", "avengers": "#c8102e"
}


def art_placeholder(theme: str, name: str) -> str:
    accent = ART_ACCENT.get(theme, "#333")
    label = name.replace('-', ' ').upper()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 560" '
        'preserveAspectRatio="xMidYMid slice">'
        f'<rect width="400" height="560" fill="#101320"/>'
        f'<path d="M0 560L260 0h140v560z" fill="{accent}" opacity=".55"/>'
        f'<path d="M0 560L120 300 220 560z" fill="{accent}" opacity=".9"/>'
        '<rect x="14" y="14" width="372" height="532" fill="none" '
        'stroke="#fff" stroke-width="4"/>'
        f'<text x="200" y="270" fill="#fff" font-family="Impact,sans-serif" '
        f'font-size="44" text-anchor="middle">{label}</text>'
        '<text x="200" y="304" fill="#fff" font-family="sans-serif" '
        'font-size="16" text-anchor="middle">ARTWORK PLACEHOLDER</text>'
        f'<text x="200" y="520" fill="#fff" font-family="monospace" '
        f'font-size="15" text-anchor="middle">art/{theme}/{name}.jpg</text>'
        '</svg>'
    )


@ui.route('/art/<theme>/<name>', methods=methods)
def ui_art(theme: str, name: str):
    if not (fullmatch(r'[a-z0-9-]{1,40}', theme)
            and fullmatch(r'[a-z0-9-]{1,40}', name)):
        return '', 404

    root = environ.get('KAPOWARR_ART_DIR') or folder_path(
        'frontend', 'static', 'art'
    )
    for ext in ('webp', 'jpg', 'jpeg', 'png', 'avif'):
        path = join(root, theme, f'{name}.{ext}')
        if isfile(path):
            return send_file(path, max_age=0)

    return Response(
        art_placeholder(theme, name),
        mimetype='image/svg+xml',
        headers={'Cache-Control': 'no-cache'}
    )


@ui.route('/login', methods=methods)
def ui_login():
    return render('login.html')


@ui.route('/', methods=methods)
def ui_volumes():
    return render('volumes.html')


@ui.route('/add', methods=methods)
def ui_add_volume():
    return render('add_volume.html')


@ui.route('/library-import', methods=methods)
def ui_library_import():
    return render('library_import.html')


@ui.route('/volumes/<id>', methods=methods)
def ui_view_volume(id):
    return render('view_volume.html')


@ui.route('/activity/queue', methods=methods)
def ui_queue():
    return render('queue.html')


@ui.route('/activity/history', methods=methods)
def ui_history():
    return render('history.html')


@ui.route('/activity/blocklist', methods=methods)
def ui_blocklist():
    return render('blocklist.html')


@ui.route('/system/status', methods=methods)
def ui_status():
    return render('status.html')


@ui.route('/system/tasks', methods=methods)
def ui_tasks():
    return render('tasks.html')


@ui.route('/system/backups', methods=methods)
def ui_backup():
    return render('backups.html')


@ui.route('/settings', methods=methods)
def ui_settings():
    return redirect(f'{Server.url_base}/settings/mediamanagement')


@ui.route('/settings/mediamanagement', methods=methods)
def ui_mediamanagement():
    return render('settings_mediamanagement.html')


@ui.route('/settings/indexers', methods=methods)
def ui_indexers():
    return render('settings_indexers.html')


@ui.route('/settings/download', methods=methods)
def ui_download():
    return render('settings_download.html')


@ui.route('/settings/downloadclients', methods=methods)
def ui_download_clients():
    return render('settings_download_clients.html')


@ui.route('/settings/metadata', methods=methods)
def ui_metadata():
    return render('settings_metadata.html')


@ui.route('/settings/general', methods=methods)
def ui_general():
    return render('settings_general.html')


@ui.route('/extras', methods=methods)
def ui_extras():
    return render('extras.html')
