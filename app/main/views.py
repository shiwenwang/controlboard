from flask import (Blueprint, render_template, redirect,
                   url_for, current_app, g)
from flask_login import current_user, login_required
from flask_uploads import configure_uploads, patch_request_class
from app.models import load_user, Task
from app.forms import NewTaskForm, EditTaskForm, DeleteTaskForm
from app import usets, db

import os
import shutil

from app.extend.bladed import Bladed
from app.extend.symbol import SymbolDB

main = Blueprint('main', __name__)


@main.route('/', methods=['GET', 'POST'])
@main.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    user = load_user(current_user.get_id())
    new_task_form = NewTaskForm()
    new_task_form.symbol.choices = get_symbol_choices()
    if new_task_form.save_submit.data and new_task_form.validate():
        create_new_task(user, new_task_form)
        return redirect(url_for('main.index'))

    edit_task_form = EditTaskForm()
    edit_task_form.symbol.choices = new_task_form.symbol.choices
    if edit_task_form.save_modify_submit.data and edit_task_form.validate():
        update_task(user, edit_task_form)
        return redirect(url_for('main.index'))

    delete_task_form = DeleteTaskForm()
    if delete_task_form.delete_submit.data and delete_task_form.validate():
        delete_task(user, delete_task_form)
        return redirect(url_for('main.index'))

    return render_template('index.html', title='主页', user=user,
                           new_task_form=new_task_form, 
                           edit_task_form=edit_task_form,
                           delete_task_form=delete_task_form)


def modify_config(user, new_task_form):
    cfg = current_app.config
    for uset in usets:
        dest_name = 'UPLOADED_%s_' % uset.name.upper() + 'DEST'

        if eval('new_task_form.' + uset.name + '.data'):
            new_destination = os.path.join(
                cfg.get('UPLOADS_DEFAULT_DEST'), user.username, new_task_form.taskname.data)
            cfg.update({dest_name: new_destination})

    configure_uploads(current_app, usets)
    patch_request_class(current_app)


def reset_config():
    cfg = current_app.config
    for uset in usets:
        dest_name = 'UPLOADED_%s_' % uset.name.upper() + 'DEST'
        cfg.update({dest_name: cfg.get('UPLOADS_DEFAULT_DEST')})

    configure_uploads(current_app, usets)
    patch_request_class(current_app)


def create_new_task(user, new_task_form):
    modify_config(user, new_task_form)

    saved_files = files_save(new_task_form)

    uset_bladed, uset_symbol, uset_xml = usets
    local_bladed_path = os.path.join(
        uset_bladed.config.destination, new_task_form.bladed.data.filename)

    task = Task(name=new_task_form.taskname.data.strip(),
                status="New",
                bladed_version=Bladed(local_bladed_path).version(),
                user_id=user.id,
                bladed_filename=saved_files['bladed']['filename'],
                bladed_url=saved_files['bladed']['url'],
                xml_filename="" if saved_files['xml'] is None else saved_files['xml']['filename'],
                xml_url="" if saved_files['xml'] is None else saved_files['xml']['url'],
                symbol_index=new_task_form.symbol.data,
                symbol_filename="" if saved_files['symbol'] is None else saved_files['symbol']['name'],
                symbol_url="" if saved_files['symbol'] is None else saved_files['symbol']['url']
                )

    db.session.add(task)
    db.session.commit()

    if saved_files['symbol'] is not None:
        cfg = current_app.config
        local_symbol_path = os.path.join(
            uset_symbol.config.destination, os.listdir(cfg.get('UPLOADS_TEMPL_DEST'))[new_task_form.symbol.data-1])
        db_symbol = SymbolDB()
        db_symbol.load_sym(local_symbol_path, db_name=task.name)
        db_symbol.create_db()

    reset_config()


def update_task(user, edit_task_form):
    modify_config(user, edit_task_form)

    uset_bladed, uset_symbol, uset_xml = usets

    task_name = edit_task_form.taskname.data
    task = Task.query.filter_by(name=task_name).first()
    if task is not None:
        saved_files = files_save(edit_task_form, task)

        if saved_files['bladed'] is not None:
            local_bladed_path = os.path.join(
                uset_bladed.config.destination, edit_task_form.bladed.data.filename)
            task.bladed_version = Bladed(local_bladed_path).version()
            task.bladed_filename = saved_files['bladed']['filename']
            task.bladed_url = saved_files['bladed']['url']
        if saved_files['xml'] is not None:
            task.xml_filename = saved_files['xml']['filename']
            task.xml_url = saved_files['xml']['url']
        if saved_files['symbol'] is not None and edit_task_form.symbol.data != task.symbol_index:
            task.symbol_index = saved_files['symbol']['index']
            task.symbol_filename = saved_files['symbol']['name']
            task.symbol_url = saved_files['symbol']['url']

            cfg = current_app.config
            local_symbol_path = os.path.join(
                uset_symbol.config.destination,
                os.listdir(cfg.get('UPLOADS_TEMPL_DEST'))[edit_task_form.symbol.data - 1])
            local_db_symbol_path = os.path.join(os.path.split(local_symbol_path)[0], task_name + '.db')
            if os.path.isfile(local_db_symbol_path):
                os.remove(local_db_symbol_path)
            db_symbol = SymbolDB()
            db_symbol.load_sym(local_symbol_path, db_name=task_name)
            db_symbol.create_db()
            db_symbol.close()

    db.session.commit()
    reset_config()


def get_symbol_choices():
    symbols_dir = current_app.config.get('UPLOADS_TEMPL_DEST')
    symbol_choices = [(0, "未选择")]
    for i, file in enumerate(os.listdir(symbols_dir)):
        symbol_choices.append((i + 1, '.'.join(file.split('.')[:-1])))

    return symbol_choices


def files_save(form, task=None):
    uset_bladed, uset_symbol, uset_xml = usets
    saved_files = {'bladed': None, 'xml': None, 'symbol': None}

    if form.bladed.data:
        if task is not None:
            delete_file(uset_bladed.config.destination, ['.$pj', '.$prj'])
        bladed_filename = uset_bladed.save(
            form.bladed.data, name=form.bladed.data.filename)
        saved_files['bladed'] = {'filename': bladed_filename,
                                 'url': uset_bladed.url(bladed_filename)}
    if form.xml.data:
        if task is not None:
            delete_file(uset_xml.config.destination, ['.xml'])
        xml_filename = uset_xml.save(
            form.xml.data, name=form.xml.data.filename)
        saved_files['xml'] = {'filename': xml_filename,
                              'url': uset_xml.url(xml_filename)}

    symbols_dir = current_app.config.get('UPLOADS_TEMPL_DEST')
    symbol_index = form.symbol.data

    if symbol_index > 0:
        if task is not None and symbol_index != task.symbol_index:
            delete_file(uset_symbol.config.destination, ['.xls', '.xlsx'])

        select_file_path = os.path.join(
            symbols_dir, os.listdir(symbols_dir)[symbol_index - 1])
        shutil.copy(select_file_path, uset_symbol.config.destination)
        saved_files['symbol'] = {'index': symbol_index,
                                 'name': os.path.split(select_file_path)[1],
                                 'url': uset_symbol.url(uset_symbol.name)}

    return saved_files


def delete_file(folder, exts):
    for f in os.listdir(folder):
        if os.path.splitext(f)[-1].lower() in exts:
            os.remove(os.path.join(folder, f))


def delete_task(user, delete_task_form):
    taskname = delete_task_form.taskname.data
    task = Task.query.filter_by(name=taskname).first()
    if task is not None:
        db.session.delete(task)
        db.session.commit()

    if delete_task_form.delete_files.data:
        cfg = current_app.config
        destination = os.path.join(cfg.get('UPLOADS_DEFAULT_DEST'), user.username, taskname)
        if os.path.isdir(destination):
            shutil.rmtree(destination)
