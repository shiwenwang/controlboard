from flask import (Blueprint, render_template, redirect, request,
                   url_for, current_app, session, jsonify, abort)
from flask_login import current_user, login_required
from flask_uploads import configure_uploads, patch_request_class
from app.models import load_user, Task
from app.forms import NewTaskForm, EditTaskForm, DeleteTaskForm
from app import usets, db
from app.extend.git import git_init, git_commit_push, git_remove_push, git_exists
from app.extend.symbol import XML

import os
import re
import shutil

from app.extend.bladed import Bladed
from app.extend.symbol import SymbolDB

main = Blueprint('main', __name__)


@main.route('/', methods=['GET', 'POST'])
@main.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    user = load_user(current_user.get_id())
    tasks_amount = len(Task.query.filter_by(user_id=user.id).all())
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

    return render_template('index.html', title='主页', user=user, tasks_amount=tasks_amount,
                           new_task_form=new_task_form,
                           edit_task_form=edit_task_form,
                           delete_task_form=delete_task_form)


@main.route('/compare/contrast', methods=['GET', 'POST'])
def contrast():
    if request.method == "POST":
        file1_text = request.files.getlist("xml-files")[0].read().decode()
        file2_text = request.files.getlist("xml-files")[1].read().decode()
        xml = XML()
        xml1_data = xml.parse_string(file1_text)
        xml2_data = xml.parse_string(file2_text)
        diff = find_diff(xml1_data, xml2_data)

        data = {'xml1': xml1_data, 'xml2': xml2_data, 'diff': diff}
        return jsonify(data)

    return jsonify({})


@main.route('/compare')
def compare():
    return render_template('compare.html', title="compare")


def find_diff(data1, data2):
    import pandas as pd   
    set1 = set(data1.keys())
    set2 = set(data2.keys())
    for name in set.union(set1.difference(set2), set2.difference(set1)):
        if name not in data1.keys():
            data1[name] = '-' if 'P_' in name else {}
        if name not in data2.keys():
            data2[name] = '-' if 'P_' in name else {}

    diff = [k for k, v in data1.items() if (isinstance(v, str) and v != data2[k]) or
            (isinstance(v, pd.DataFrame) and not all(v == data2[k]))]
    diff.extend(list(set.union(set1.difference(set2), set2.difference(set1))))

    return diff


def modify_config(user, new_task_form):
    cfg = current_app.config
    for uset in usets:
        dest_name = 'UPLOADED_%s_' % uset.name.upper() + 'DEST'

        if eval('new_task_form.' + uset.name + '.data'):
            new_destination = os.path.abspath(os.path.join(
                cfg.get('UPLOADS_DEFAULT_DEST'), user.username, new_task_form.taskname.data))
            cfg.update({dest_name: new_destination})

    configure_uploads(current_app, usets)
    patch_request_class(current_app)


def reset_config():
    cfg = current_app.config
    for uset in usets:
        dest_name = 'UPLOADED_%s_' % uset.name.upper() + 'DEST'
        cfg.update({dest_name: os.path.abspath(cfg.get('UPLOADS_DEFAULT_DEST'))})

    configure_uploads(current_app, usets)
    patch_request_class(current_app)


def create_new_task(user, new_task_form):
    uset_bladed, uset_symbol, uset_xml = usets
    modify_config(user, new_task_form)
    taskname = new_task_form.taskname.data.strip()
    destination = uset_bladed.config.destination
    isgitted = new_task_form.add_to_git.data

    cfg = current_app.config
    git_path = os.path.abspath(os.path.join(cfg.get('UPLOADS_DEFAULT_DEST'), user.username))
    if not git_exists(git_path):
        git_init(git_path, user.username, isgitted, newfolder=taskname)  # 初始化

    saved_files = files_save(new_task_form)

    if not isgitted:
        gitignore_path = os.path.join(git_path, '.gitignore')
        with open(gitignore_path, 'a+') as f:
            f.write(f'\n{taskname}/')

    git_commit_push(git_path, "D0")  # 添加并提交文件
    local_bladed_path = os.path.join(destination, new_task_form.bladed.data.filename)

    task = Task(name=taskname,
                status="New",
                bladed_version=Bladed(local_bladed_path).version,
                user_id=user.id,
                isgitted=int(isgitted),
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
        local_symbol_path = os.path.abspath(os.path.join(uset_symbol.config.destination, task.symbol_filename))
        db_symbol = SymbolDB()
        db_symbol.load_sym(local_symbol_path, db_name=task.name)
        db_symbol.create_db()

    reset_config()


def update_task(user, edit_task_form):
    modify_config(user, edit_task_form)

    uset_bladed, uset_symbol, uset_xml = usets
    destination = uset_bladed.config.destination

    task_name = edit_task_form.taskname.data
    task = Task.query.filter_by(name=task_name).first()
    new_file = False
    if task is not None:
        saved_files = files_save(edit_task_form, task)

        if saved_files['bladed'] is not None:
            new_file = True
            local_bladed_path = os.path.join(destination, edit_task_form.bladed.data.filename)
            task.bladed_version = Bladed(local_bladed_path).version
            task.bladed_filename = saved_files['bladed']['filename']
            task.bladed_url = saved_files['bladed']['url']
        if saved_files['xml'] is not None:
            new_file = True
            task.xml_filename = saved_files['xml']['filename']
            task.xml_url = saved_files['xml']['url']
        if saved_files['symbol'] is not None and edit_task_form.symbol.data != task.symbol_index:
            new_file = True
            task.symbol_index = saved_files['symbol']['index']
            task.symbol_filename = saved_files['symbol']['name']
            task.symbol_url = saved_files['symbol']['url']

            symbols_dir = os.path.abspath(uset_symbol.config.destination)
            symbol_full_path = findfile(symbols_dir, task.symbol_filename)
            local_db_symbol_path = os.path.join(os.path.split(symbol_full_path)[0], task_name + '.db')
            if os.path.isfile(local_db_symbol_path):
                os.remove(local_db_symbol_path)
            db_symbol = SymbolDB()
            db_symbol.load_sym(symbol_full_path, db_name=task_name)
            db_symbol.create_db()
            db_symbol.close()

    db.session.commit()
    cfg = current_app.config
    git_path = os.path.abspath(os.path.join(cfg.get('UPLOADS_DEFAULT_DEST'), user.username))
    if new_file and task and task.isgitted:
        commit_str = []
        if edit_task_form.bladed.data:
            commit_str.append("重新上传Bladed模型，并删除旧模型。")
        if edit_task_form.xml.data:
            commit_str.append("重新上传XML文件，并删除所有历史XML文件。")

        git_commit_push(git_path, " ".join(commit_str) if commit_str else "一次滞后提交。")
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
            delete_file(uset_bladed.config.destination, ['.$pj', '.prj'])
        bladed_filename = uset_bladed.save(
            form.bladed.data, name=form.bladed.data.filename)
        saved_files['bladed'] = {'filename': bladed_filename,
                                 'url': uset_bladed.url(bladed_filename)}
    if form.xml.data:
        if task is not None:
            delete_file(uset_xml.config.destination, ['.xml'])
        xml_filename = uset_xml.save(
            form.xml.data, name=form.taskname.data + '.xml')  # form.xml.data.filename)
        saved_files['xml'] = {'filename': xml_filename,
                              'url': uset_xml.url(xml_filename)}

    symbol_index = form.symbol.data
    if symbol_index > 0:
        filename = form.symbol.choices[symbol_index][1]

        if task is not None and filename != task.symbol_filename:
            symbols_dir = os.path.abspath(current_app.config.get('UPLOADS_TEMPL_DEST'))
            symbol_full_path = findfile(symbols_dir, filename)

            target_dir = os.path.abspath(uset_symbol.config.destination)
            if task.symbol_index > 0:
                delete_file(target_dir, ['.xls', '.xlsx'])

            shutil.copy(symbol_full_path, target_dir)

            saved_files['symbol'] = {'index': symbol_index,
                                     'name': filename,
                                     'url': uset_symbol.url(uset_symbol.name)}

    return saved_files


def delete_file(folder, exts):
    for f in os.listdir(folder):
        if os.path.splitext(f)[-1].lower() in exts:
            os.remove(os.path.join(folder, f))


def delete_task(user, delete_task_form):
    taskname = delete_task_form.taskname.data
    task = Task.query.filter_by(name=taskname).first()
    cfg = current_app.config
    destination = os.path.abspath(os.path.join(cfg.get('UPLOADS_DEFAULT_DEST'), user.username, taskname))
    git_path = os.path.abspath(os.path.join(cfg.get('UPLOADS_DEFAULT_DEST'), user.username))

    if task is not None:
        db.session.delete(task)
        db.session.commit()

    if delete_task_form.delete_files.data:
        files_to_rm = []
        for f in os.listdir(destination):
            if os.path.splitext(f)[-1] in ['.xlsx', '.xls', 'xml']:
                files_to_rm.append('/'.join([taskname, f]))
        if task.isgitted:
            git_remove_push(git_path, files_to_rm)
        if os.path.isdir(destination):
            shutil.rmtree(destination)


def findfile(start, name):
    for relpath, dirs, files in os.walk(start):
        if f'{name}.xlsx' in files:
            full_path = os.path.join(start, relpath, f'{name}.xlsx')
            return os.path.abspath(full_path)
        if f'{name}.xls' in files:
            full_path = os.path.join(start, relpath, f'{name}.xls')
            return os.path.abspath(full_path)
