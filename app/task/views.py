from flask import (Blueprint, jsonify, render_template, request, abort, g,
                   current_app, redirect, url_for, send_from_directory)
from flask_login import current_user, login_required
from sqlalchemy import and_, or_
from app.forms import NewTaskForm, EditTaskForm, WorkingForm
from app.models import User, Task, load_user
from app.extend.symbol import SymbolDB, XML
from app.extend.bladed import Bladed, Mode
from app.extend.git import git_commit_push
from app import db

import os
import re
import json
import shutil
import time
from collections import OrderedDict
from datetime import datetime
from multiprocessing import Process
from zipfile import ZipFile

task = Blueprint('task', __name__, url_prefix='/task')


@task.route('validate/name_exist', methods=['GET', 'POST'])
@login_required
def name_exist_validate():
    form = NewTaskForm()
    result = {'exist': False}
    task_name = form.taskname.data
    if not task_name.strip():
        result['empty'] = True
    task = Task.query.filter_by(name=task_name.strip()).first()
    if task is not None:
        result['exist'] = True
        result['empty'] = False

    return jsonify(result)


@task.route('validate/name_empty', methods=['GET', 'POST'])
@login_required
def name_empty_validate():
    form = NewTaskForm()
    task_name = form.taskname.data
    if task_name and not task_name.strip():
        return jsonify(False)
    return jsonify(True)


@task.route('table', methods=['GET', 'POST'])
@login_required
def table_data():
    data = {}
    if request.method == 'GET':
        return jsonify(data)

    user = load_user(current_user.get_id())
    filters = request.json['filter'] if request.json['filter'] else [
        "任务名", "创建人", "任务状态", "Bladed版本"]
    search_key = request.json['search_key']
    if search_key:
        sql_ele = eval(search_by(filters, search_key))
        if not isinstance(sql_ele, tuple):
            sql_ele = tuple([sql_ele])
        if request.json['filter']:
            all_tasks = Task.query.filter(and_(*sql_ele))
            user_tasks = Task.query.filter(
                and_(Task.user_id.is_(user.id), and_(*sql_ele)))
        else:
            all_tasks = Task.query.filter(or_(*sql_ele))
            user_tasks = Task.query.filter(
                and_(Task.user_id.is_(user.id), or_(*sql_ele)))
    else:
        all_tasks = Task.query.all()
        user_tasks = Task.query.filter_by(user_id=user.id)

    data['all'] = [tsk.to_json(i + 1) for i, tsk in enumerate(all_tasks[::-1])]
    data['user'] = [tsk.to_json(i + 1)
                    for i, tsk in enumerate(user_tasks[::-1])]

    return jsonify(data)


@task.route('info', methods=['GET', 'POST'])
@login_required
def task_info():
    info = {}
    form = EditTaskForm()
    task_name = form.taskname.data
    _task = Task.query.filter_by(name=task_name).first()
    turbine_platform, turbine_model, blade_model, tower_type = tuple(
        re.split(r'[\\/]', _task.controller_src)[-4:])
    if task is not None:
        info['bladed'] = _task.bladed_filename
        info['turbine_platform'] = turbine_platform
        info['turbine_model'] = turbine_model
        info['blade_model'] = blade_model
        info['tower_type'] = tower_type

    return jsonify(info)


@task.route('enter', methods=['POST'])
@login_required
def enter():
    taskname = request.json
    _task = Task.query.filter_by(name=taskname).first()

    if _task is not None:
        if _task.status == 'New' and _task.isgitted:
            _task.status = 'Clean'
        db.session.commit()
        return jsonify({})
    else:
        abort(404)


def search_by(filters, search_key):
    search_key = search_key.strip()
    filter_map = {"任务名": "name", "创建人": "user",
                  "任务状态": "status", "Bladed版本": "bladed_version"}
    filter_statements = []

    for _filter in filters:
        if '创建人' == _filter:
            users = User.query.filter(
                User.realname.like(f"%{search_key}%")).all()
            for user in users:
                filter_statements.append(f'Task.user_id.is_({user.id})')
            continue

        filter_statements.append(
            f'Task.{filter_map[_filter]}.like("%{search_key}%")')

    return ', '.join(filter_statements)


@task.route('work/<taskname>', methods=['GET', 'POST'])
@login_required
def work(taskname):
    # user = load_user(current_user.get_id())
    _task = Task.query.filter_by(name=taskname).first()
    user = User.query.filter_by(id=_task.user_id).first()
    tasks_amount = len(Task.query.filter_by(user_id=user.id).all())
    if _task is None:
        abort(404)

    working_form = WorkingForm()
    if working_form.save_submit.data and working_form.validate():
        pass
        return redirect(url_for('task.work', taskname=taskname))
    if working_form.download_submit.data and working_form.validate():
        pass
        return redirect(url_for('task.work', taskname=taskname))

    return render_template('task_working.html', user=user, tasks_amount=tasks_amount,
                           task=_task, title=taskname, working_form=working_form)


@task.route('read/<taskname>', methods=['GET', 'POST'])
@login_required
def initial_value(taskname):
    _task = Task.query.filter_by(name=taskname).first()
    user = User.query.filter_by(id=_task.user_id).first()
    dest = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), taskname)

    bladed = Bladed(os.path.join(dest, _task.bladed_filename))
    only_in_bladed = ['P_DMGT']

    with current_app.open_instance_resource('name_mapping.json') as f:
        symbols_name = OrderedDict(json.load(f))

    symbols_value = {'params': [], 'filters': [], 'schedules': []}

    symbols_db_path = os.path.join(current_app.instance_path, 'symbols.db')

    pattern = re.compile(r'\d+$')
    symbols = SymbolDB()
    symbols.load_db(symbols_db_path)
    symbols.connect()

    p_name = [p for p in symbols_name.keys(
    ) if 'P_' in p and p not in only_in_bladed]
    f_name = [p for p in symbols_name.keys() if 'F_' in p]
    t_name = [p for p in symbols_name.keys() if 'T_' in p]
    p_queried = symbols.multi_query(p_name)
    f_queried = symbols.multi_query(f_name)
    t_queried = symbols.multi_query(t_name)
    symbols.close()

    t_queried = {pattern.sub("", k, 1): v for k, v in t_queried.items()}
    f_queried = {pattern.sub("", k, 1): v for k, v in f_queried.items()}

    xml_path = os.path.join(dest, _task.xml_filename)
    xml = XML()
    try:
        xml.open(xml_path)
    except FileNotFoundError:
        return jsonify(symbols_value)

    xml_values = {}
    for name in symbols_name.keys():
        if name in only_in_bladed:
            xml_values[name] = ""
            continue
        xml_values.update(xml.find(name))

    if task is not None:
        for name, value in xml_values.items():
            if 'P_' in name:
                symbols_value['params'].append({
                    'name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                    f'{p_queried[name].at["Description_en_GB"] if name not in only_in_bladed and name in p_queried.keys() else symbols_name[name]["description_zh"]}'
                    f'">{name}</span>',
                    'bladed_value': '-' if not symbols_name[name]['bladed'] else
                    f'<input type="text" class="table-value-bladed text-primary" id="{name}-bladed" disabled value="{bladed.query(symbols_name[name]["bladed"])[1]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    'symbol_value': '-' if name in only_in_bladed else
                    f'<input type="text" class="table-value text-primary" id="{name}-symbol" disabled value="{value}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    'description': symbols_name[name]["description_zh"]
                })
            if 'T_' in name:
                for index in value.index:
                    symbols_value['schedules'].append({
                        'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                        f'{t_queried[name].at["Description_en_GB"]}">{name}</span>',
                        'Enabled':
                            f'<input type="text" class="table-value enable-col  text-danger" id="{name}{index}-Enabled" disabled value="{value.at[0, "Enabled"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:50px;" onchange="checkChanged()">',
                        'Display_Name': '-',
                        '0': '-' if '_0' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-0" disabled value="{value.at[index, "_0"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        '1': '-' if '_1' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-1" disabled value="{value.at[index, "_1"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        '2': '-' if '_2' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-2" disabled value="{value.at[index, "_2"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        '3': '-' if '_3' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-3" disabled value="{value.at[index, "_3"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        '4': '-' if '_4' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-4" disabled value="{value.at[index, "_4"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        '5': '-' if '_5' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-5" disabled value="{value.at[index, "_5"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        '6': '-' if '_6' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-6" disabled value="{value.at[index, "_6"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        '7': '-' if '_7' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-7" disabled value="{value.at[index, "_7"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        '8': '-' if '_8' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-8" disabled value="{value.at[index, "_8"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        '9': '-' if '_9' not in value.columns else
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-9" disabled value="{value.at[index, "_9"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">'
                    })
            if 'F_' in name:
                for index in value.index:
                    symbols_value['filters'].append({
                        'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                        f'{f_queried[name].at["Description_en_GB"]}">{name}</span>',
                        'Enabled':
                        f'<input type="text" class="table-value enable-col text-danger" id="{name}{index}-Enabled" disabled value="{value.at[index, "Enabled"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:50px;" onchange="checkChanged()">',
                        'Display_Name': f'{index+1}',
                        'Numerator_Type': value.at[index, "Numerator_Type"],
                        'Denominator_Type': value.at[index, "Denominator_Type"],
                        'Numerator_TC': value.at[index, "Numerator_TC"],
                        # f'<input type="text" class="table-value" disabled value="{value.at[index, "Numerator_TC"]}"'
                        # f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                        'Denominator_TC': value.at[index, "Denominator_TC"],
                        # f'<input type="text" class="table-value" disabled value="{value.at[index, "Denominator_TC"]}"'
                        # f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                        'Numerator_Frequency':
                        f'<input type="text" class="table-value num-frequency-col text-primary" id="{name}{index}-Numerator_Frequency" disabled value="{value.at[index, "Numerator_Frequency"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onkeyup="equals(\'{name}{index}-Numerator_Frequency\', \'{name}{index}-Denominator_Frequency\')" onchange="checkChanged()">',
                        'Numerator_Damping_Ratio':
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-Numerator_Damping_Ratio" disabled value="{value.at[index, "Numerator_Damping_Ratio"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        'Denominator_Frequency':
                        f'<input type="text" class="table-value den-frequency-col text-primary" id="{name}{index}-Denominator_Frequency" disabled value="{value.at[index, "Denominator_Frequency"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onkeyup="equals(\'{name}{index}-Denominator_Frequency\', \'{name}{index}-Numerator_Frequency\')" onchange="checkChanged()">',
                        'Denominator_Damping_Ratio':
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-Denominator_Damping_Ratio" disabled value="{value.at[index, "Denominator_Damping_Ratio"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        'W0':
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-W0" disabled value="{value.at[index, "W0"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                        'Prewarping_Wc':
                        f'<input type="text" class="table-value text-primary" id="{name}{index}-Prewarping_Wc" disabled value="{value.at[index, "Prewarping_Wc"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    })

    return jsonify(symbols_value)


# @task.route('write/<taskname>/<obj>', methods=['GET', 'POST'])
@task.route('write/<taskname>', methods=['GET', 'POST'])
@login_required
def set_value(taskname):
    _task = Task.query.filter_by(name=taskname).first()
    user = User.query.filter_by(id=_task.user_id).first()
    # dest = os.path.join(current_app.config.get(
    #     'UPLOADS_DEFAULT_DEST'), user.username, taskname)
    dest = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), taskname)
    _task.status = "Working"
    data = request.json['data']
    isgitted = request.json['isgitted']
    description = request.json['description'] if request.json['description'] else "Updated"
    cfg = current_app.config
    # git_path = os.path.join(cfg.get('UPLOADS_DEFAULT_DEST'), user.username)
    git_path = os.path.join(cfg.get('UPLOADS_DEFAULT_DEST'))

    bladed_data = {k.split('-')[0]: v['new'].strip()
                   for k, v in data.items() if '-bladed' in k}
    symbol_data = {k: v['new'].strip() for k, v in data.items() if '-bladed' not in k}

    if bladed_data:
        with current_app.open_instance_resource('name_mapping.json') as f:
            symbols_name = OrderedDict(json.load(f))

        bladed = Bladed(os.path.join(dest, _task.bladed_filename))
        bladed_args = {symbols_name[k]['bladed']
            : v for k, v in bladed_data.items()}
        bladed.set(**bladed_args)

    new_name = request.json['newname'] if os.path.splitext(request.json['newname'])[-1] in ['.xml'] else \
        request.json['newname'] + '.xml'
    new_name_path = os.path.join(dest, new_name)
    xml_path = os.path.join(dest, _task.xml_filename)
    if xml_path != new_name_path:
        shutil.copy(xml_path, new_name_path)
        _task.xml_filename = new_name
    xml = XML()
    try:
        xml.open(new_name_path)
    except FileNotFoundError:
        return None
    fine_data = {}
    pattern = re.compile(r'^(\S+?)(\d*)-(\S+)$')
    for name, data in symbol_data.items():
        m = pattern.search(name)
        true_name, row, col = m.groups()
        col = f'_{col}' if col.isdigit() else col.replace('_', '')

        if true_name not in fine_data.keys():
            fine_data[true_name] = {row: {col: data}}
        else:
            if row not in fine_data[true_name].keys():
                fine_data[true_name][row] = {col: data}
            else:
                fine_data[true_name][row].update({col: data})

    p_list = [p for p in symbol_data if 'P_' in p]
    t_list = [p for p in symbol_data if 'P_' not in p]
    xml.update(p_list, t_list, **fine_data)

    readme_text = os.path.join(dest, 'README.txt')
    with open(readme_text, 'a', encoding='utf-8') as f:
        f.write(description)

    _task.status = "Dirty" if _task.isgitted else "Saved"

    if isgitted:  # 提交至Git并push
        git_commit_push(git_path, description)
        _task.status = "Clean"

    return initial_value(taskname)


@task.route('search/<taskname>', methods=['POST'])
@login_required
def search_list(taskname):
    _task = Task.query.filter_by(name=taskname).first()
    user = User.query.filter_by(id=_task.user_id).first()
    dest = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), taskname)

    key_word = request.json.strip()
    names = []

    if key_word:
        xml_path = os.path.join(dest, _task.xml_filename)
        xml = XML()
        try:
            xml.open(xml_path)
        except FileNotFoundError:
            return None

        names = xml.query(key_word, name_only=True)

    return jsonify(names)


@task.route('search/<taskname>/<param>', methods=['POST'])
@login_required
def search(taskname, param):
    _task = Task.query.filter_by(name=taskname).first()
    user = User.query.filter_by(id=_task.user_id).first()
    dest = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), taskname)

    symbols_value = {'params': [], 'filters': [], 'schedules': []}

    symbols_db_path = os.path.join(current_app.instance_path, 'symbols.db')

    pattern = re.compile(r'\d+$')
    symbols = SymbolDB()
    symbols.load_db(symbols_db_path)
    symbols.connect()
    queried = symbols.multi_query([param])
    symbols.close()

    queried = {pattern.sub("", k, 1): v for k, v in queried.items()}

    xml_path = os.path.join(dest, _task.xml_filename)
    xml = XML()
    try:
        xml.open(xml_path)
    except FileNotFoundError:
        return jsonify(symbols_value)

    xml_values = xml.find(param)
    value = xml_values[param]

    if task is not None:
        if 'P_' in param:
            symbols_value['params'].append({
                'name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{queried[param].at["Description_en_GB"] if param in queried.keys() else param}">{param}</span>',
                'bladed_value': '-',
                'symbol_value':
                f'<input type="text" class="table-value text-primary" id="{param}-symbol" disabled value="{value}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'description': ""
            })
        if 'T_' in param:
            for index in value.index:
                symbols_value['schedules'].append({
                    'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                    f'{queried[param].at["Description_en_GB"] if param in queried.keys() else param}">{param}</span>',
                    'Enabled':
                        f'<input type="text" class="table-value enable-col  text-danger" id="{param}{index}-Enabled" disabled value="{value.at[0, "Enabled"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                    'Display_Name': '-',
                    '0': '-' if '_0' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-0" disabled value="{value.at[index, "_0"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    '1': '-' if '_1' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-1" disabled value="{value.at[index, "_1"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    '2': '-' if '_2' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-2" disabled value="{value.at[index, "_2"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    '3': '-' if '_3' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-3" disabled value="{value.at[index, "_3"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    '4': '-' if '_4' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-4" disabled value="{value.at[index, "_4"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    '5': '-' if '_5' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-5" disabled value="{value.at[index, "_5"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    '6': '-' if '_6' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-6" disabled value="{value.at[index, "_6"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    '7': '-' if '_7' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-7" disabled value="{value.at[index, "_7"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    '8': '-' if '_8' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-8" disabled value="{value.at[index, "_8"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    '9': '-' if '_9' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-9" disabled value="{value.at[index, "_9"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">'
                })
        if 'F_' in param:
            for index in value.index:
                symbols_value['filters'].append({
                    'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                    f'{queried[param].at["Description_en_GB"] if param in queried.keys() else param}">{param}</span>',
                    'Enabled':
                    f'<input type="text" class="table-value enable-col text-danger" id="{param}{index}-Enabled" disabled value="{value.at[index, "Enabled"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                    'Display_Name': f'{index+1}',
                    'Numerator_Type': value.at[index, "Numerator_Type"],
                    'Denominator_Type': value.at[index, "Denominator_Type"],
                    'Numerator_TC': value.at[index, "Numerator_TC"],
                    # f'<input type="text" class="table-value" disabled value="{value.at[index, "Numerator_TC"]}"'
                    # f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    'Denominator_TC': value.at[index, "Denominator_TC"],
                    # f'<input type="text" class="table-value" disabled value="{value.at[index, "Denominator_TC"]}"'
                    # f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    'Numerator_Frequency':
                    f'<input type="text" class="table-value num-frequency-col text-primary" id="{param}{index}-Numerator_Frequency" disabled value="{value.at[index, "Numerator_Frequency"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onkeyup="equals(\'{param}{index}-Numerator_Frequency\', \'{param}{index}-Denominator_Frequency\')">',
                    'Numerator_Damping_Ratio':
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-Numerator_Damping_Ratio" disabled value="{value.at[index, "Numerator_Damping_Ratio"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    'Denominator_Frequency':
                    f'<input type="text" class="table-value den-frequency-col text-primary" id="{param}{index}-Denominator_Frequency" disabled value="{value.at[index, "Denominator_Frequency"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onkeyup="equals(\'{param}{index}-Denominator_Frequency\', \'{param}{index}-Numerator_Frequency\')">',
                    'Denominator_Damping_Ratio':
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-Denominator_Damping_Ratio" disabled value="{value.at[index, "Denominator_Damping_Ratio"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    'W0':
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-W0" disabled value="{value.at[index, "W0"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                    'Prewarping_Wc':
                    f'<input type="text" class="table-value text-primary" id="{param}{index}-Prewarping_Wc" disabled value="{value.at[index, "Prewarping_Wc"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                })

    return jsonify(symbols_value)


@task.route('download/<taskname>')
@login_required
def download(taskname):
    _task = Task.query.filter_by(name=taskname).first()
    user = User.query.filter_by(id=_task.user_id).first()
    if _task is None:
        abort(404)

    folder = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), taskname)

    ctrl_zip = os.path.join(folder, f'{taskname}.zip')
    dll_file = os.path.join(folder, _task.dll_filename)
    xml_file = os.path.join(folder, _task.xml_filename)
    readme_file = os.path.join(folder, 'README.txt')

    zip_mode = 'w' if os.path.exists(ctrl_zip) else 'a'

    with ZipFile(ctrl_zip, zip_mode) as ctrlzip:
        ctrlzip.write(dll_file, arcname=os.path.basename(dll_file))
        ctrlzip.write(xml_file, arcname=os.path.basename(xml_file))
        ctrlzip.write(readme_file, arcname=os.path.basename(readme_file))
            
    return send_from_directory(directory=folder, filename=os.path.basename(ctrl_zip), as_attachment=True)


@task.route('watch/<taskname>')
@login_required
def watch(taskname):
    _task = Task.query.filter_by(name=taskname).first()
    user = User.query.filter_by(id=_task.user_id).first()
    if _task is None:
        abort(404)

    folder = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), taskname)
    return send_from_directory(directory=folder, filename=_task.xml_filename, as_attachment=False)


@task.route('campbell/<taskname>', methods=['POST'])
@login_required
def campbell(taskname):
    _task = Task.query.filter_by(name=taskname).first()
    user = User.query.filter_by(id=_task.user_id).first()
    file_folder = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), taskname)
    calc_folder = os.path.join(current_app.config.get(
        'CALCULATION_DEST'), taskname)
    if not os.path.isdir(calc_folder):
        os.makedirs(calc_folder)
    bladed_path = os.path.abspath(
        os.path.join(file_folder, _task.bladed_filename))
    run_dir = os.path.abspath(os.path.join(calc_folder, 'campbell_run'))

    bladed = Bladed(bladed_path)
    try:
        # bladed.campbell(run_dir)
        proc_campbell = Process(target=bladed.campbell, args=(run_dir,))
        proc_campbell.start()
        return jsonify({'calc': True})
    except:
        return jsonify({'calc': False})


def check_lin1_cm(run_dir, _task):
    while not os.path.exists(os.path.join(run_dir, 'lin1.$CM')):
        time.sleep(2)
        continue


@task.route('mode_check/<taskname>', methods=['POST'])
@login_required
def mode_check(taskname):
    time.sleep(30)
    _task = Task.query.filter_by(name=taskname).first()
    user = User.query.filter_by(id=_task.user_id).first()
    calc_folder = os.path.join(current_app.config.get(
        'CALCULATION_DEST'), taskname)
    run_dir = os.path.abspath(os.path.join(calc_folder, 'campbell_run'))

    p_check = Process(target=check_lin1_cm, args=(run_dir, _task))
    p_check.start()
    p_check.join(600)  # 最长运行12分钟

    mode = Mode(run_dir)
    names = ','.join(mode.mode_names)
    freqs = ','.join(mode.get_modes()['freqs'])
    damps = ','.join(mode.get_modes()['damps'])
    _task.mode_names = names
    _task.mode_freqs = freqs
    _task.mode_damps = damps
    db.session.commit()

    result = {"completed": True} if os.path.exists(os.path.join(run_dir, 'lin1.$CM')) else \
             {"completed": False}
    return jsonify(result)


@task.route('mode/<taskname>', methods=['POST'])
@login_required
def mode(taskname):
    _task = Task.query.filter_by(name=taskname).first()

    mode_map = {
        '3.82': 'Tower side-side mode 1',
        '4.3': 'Tower mode 1',
        '4.6': 'Tower mode 1',
        '4.7': 'Tower 1st side-side mode',
    }

    if _task.mode_names is None:
        return jsonify({})
    names, freqs, damps = _task.mode_names.split(
        ','), _task.mode_freqs.split(','), _task.mode_damps.split(',')

    table_data = [{"name": name, "freq": freqs[i], "damp": damps[i]}
                  for i, name in enumerate(names)]
    modes_data = {name: freqs[i] for i, name in enumerate(names)}
    data = {"table_data": table_data, "modes": modes_data,
            "tower_mode_1": mode_map[_task.bladed_version]}

    return jsonify(data)
