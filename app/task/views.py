from flask import (Blueprint, jsonify, render_template, request, abort,
                   current_app, redirect, url_for, send_from_directory)
from flask_login import current_user, login_required
from sqlalchemy import and_, or_
from app.forms import NewTaskForm, EditTaskForm, WorkingForm
from app.models import User, Task, load_user
from app.extend.symbol import SymbolDB, XML
from app.extend.bladed import Bladed
from app import db

import os
import re
import json
from collections import OrderedDict

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


@task.route('file', methods=['GET', 'POST'])
@login_required
def file_info():
    files = {}
    form = EditTaskForm()
    task_name = form.taskname.data
    _task = Task.query.filter_by(name=task_name).first()
    if task is not None:
        files['bladed'] = {
            'filename': _task.bladed_filename, 'url': _task.bladed_url}
        files['xml'] = {'filename': _task.xml_filename, 'url': _task.xml_url}
        files['symbol'] = {
            'index': _task.symbol_index, 'url': _task.symbol_url}

    return jsonify(files)


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


@task.route('work/<taskname>/', methods=['GET', 'POST'], defaults={'obj': 'symbol'})
@task.route('work/<taskname>/<obj>', methods=['GET', 'POST'])
@login_required
def work(taskname, obj):
    user = load_user(current_user.get_id())
    tasks_amount = len(Task.query.filter_by(user_id=user.id).all())
    task = Task.query.filter_by(name=taskname).first()

    if task is not None:
        if task.status == 'New':
            task.status = 'Working'
            db.session.commit()
    else:
        abort(404)
    working_form = WorkingForm()
    if working_form.save_submit.data and working_form.validate():
        pass
        return redirect(url_for('task.work', taskname=taskname))
    if working_form.download_submit.data and working_form.validate():
        pass
        return redirect(url_for('task.work', taskname=taskname))

    return render_template('task_working.html', user=user, tasks_amount=tasks_amount, obj=obj,
                           taskname=taskname, title=taskname, working_form=working_form)


@task.route('read/<taskname>/<obj>', methods=['GET', 'POST'])
@login_required
def initial_value(taskname, obj):
    user = load_user(current_user.get_id())
    dest = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), user.username, taskname)

    _task = Task.query.filter_by(name=taskname).first()
    bladed = Bladed(os.path.join(dest, _task.bladed_filename))
    only_in_bladed = ['P_DMGT']

    with current_app.open_instance_resource('name_mapping.json') as f:
        symbols_name = OrderedDict(json.load(f))

    symbols_value = {'params': [], 'filters': [], 'schedules': []}

    if obj == "symbol":
        db_symbol_path = os.path.join(dest, taskname + '.db')
        db_symbol = SymbolDB()
        db_symbol.load_db(db_symbol_path)
        db_symbol.connect()

        p_name = [p for p in symbols_name.keys() if 'P_' in p and p not in only_in_bladed]
        f_name = [p for p in symbols_name.keys() if 'F_' in p]
        t_name = [p for p in symbols_name.keys() if 'T_' in p]
        p_queried = db_symbol.multi_query(p_name)
        f_queried = db_symbol.multi_query(f_name)
        t_queried = db_symbol.multi_query(t_name)
        db_symbol.close()

        if task is not None:
            pattern = re.compile(r'\d+$')
            # 保证显示顺序
            symbols_value['params'] = [{
                'name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{p_queried[name].at["Description_en_GB"] if name not in only_in_bladed and name in p_queried.keys() else symbols_name[name]["description_zh"]}'
                f'">{name}</span>',
                'bladed_value': '-' if not symbols_name[name]['bladed'] else
                f'<input type="text" class="table-value text-primary" id="{name}-bladed" disabled value="{bladed.query(symbols_name[name]["bladed"])[1]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'symbol_value': '-' if name in only_in_bladed or name not in p_queried.keys() else
                f'<input type="text" class="table-value text-primary" id="{name}-symbol" disabled value="{p_queried[name].at["Initial_Value"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'description': symbols_name[name]["description_zh"]
                }
                for name in symbols_name.keys() if 'P_' in name
            ]
            symbols_value['schedules'] = [{
                'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{t_queried[name].at["Description_en_GB"]}">{pattern.sub("", name, 1)}</span>',
                'Enabled':
                f'<input type="text" class="table-value enable-col  text-danger" id="{name}-Enabled" disabled value="{t_queried[name].at["Enabled"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                'Display_Name': t_queried[name].at['Display_Name'],
                '0': '-' if t_queried[name].at['_0'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-0" disabled value="{t_queried[name].at["_0"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '1': '-' if t_queried[name].at['_1'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-1" disabled value="{t_queried[name].at["_1"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '2': '-' if t_queried[name].at['_2'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-2" disabled value="{t_queried[name].at["_2"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '3': '-' if t_queried[name].at['_3'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-3" disabled value="{t_queried[name].at["_3"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '4': '-' if t_queried[name].at['_4'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-4" disabled value="{t_queried[name].at["_4"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '5': '-' if t_queried[name].at['_5'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-5" disabled value="{t_queried[name].at["_5"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '6': '-' if t_queried[name].at['_6'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-6" disabled value="{t_queried[name].at["_6"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '7': '-' if t_queried[name].at['_7'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-7" disabled value="{t_queried[name].at["_7"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '8': '-' if t_queried[name].at['_8'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-8" disabled value="{t_queried[name].at["_8"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '9': '-' if t_queried[name].at['_9'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-9" disabled value="{t_queried[name].at["_9"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">'
            } for name in t_queried.keys()
            ]
            symbols_value['filters'] = [{
                'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{f_queried[name].at["Description_en_GB"]}">{pattern.sub("", name, 1)}</span>',
                'Enabled':
                f'<input type="text" class="table-value enable-col  text-danger" id="{name}-Enabled" disabled value="{f_queried[name].at["Enabled"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                'Display_Name': f_queried[name].at["Display_Name"],
                'Numerator_Type': f_queried[name].at["Numerator_Type"],
                'Denominator_Type': f_queried[name].at["Denominator_Type"],
                'Numerator_TC': f_queried[name].at["Numerator_TC"],
                # f'<input type="text" class="table-value" disabled value="{f_queried[name].at["Numerator_TC"]}"'
                # f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Denominator_TC': f_queried[name].at["Denominator_TC"],
                # f'<input type="text" class="table-value" disabled value="{f_queried[name].at["Denominator_TC"]}"'
                # f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Numerator_Frequency':
                f'<input type="text" class="table-value text-primary frequency-col" id="{name}-Numerator_Frequency" disabled value="{f_queried[name].at["Numerator_Frequency"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Numerator_Damping_Ratio':
                f'<input type="text" class="table-value text-primary" id="{name}-Numerator_Damping_Ratio" disabled value="{f_queried[name].at["Numerator_Damping_Ratio"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Denominator_Frequency':
                f'<input type="text" class="table-value text-primary frequency-col" id="{name}-Denominator_Frequency" disabled value="{f_queried[name].at["Denominator_Frequency"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Denominator_Damping_Ratio':
                f'<input type="text" class="table-value text-primary" id="{name}-Denominator_Damping_Ratio" disabled value="{f_queried[name].at["Denominator_Damping_Ratio"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'W0':
                f'<input type="text" class="table-value text-primary" id="{name}-W0" disabled value="{f_queried[name].at["W0"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Prewarping_Wc':
                f'<input type="text" class="table-value text-primary" id="{name}-Prewarping_Wc" disabled value="{f_queried[name].at["Prewarping_Wc"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
            } for name in f_queried.keys()
            ]

    if obj == 'xml':
        xml_path = os.path.join(dest, _task.xml_filename)
        xml = XML()
        try:
            xml.open(xml_path)
        except FileNotFoundError:
            return jsonify(symbols_value)
        names = [p for p in symbols_name.keys()]
        xml_values = {}
        for name in names:
            if name in only_in_bladed:
                xml_values[name] = ""
                continue
            xml_values.update(xml.find(name))

        if task is not None:
            for name, value in xml_values.items():
                if 'P_' in name:
                    symbols_value['params'].append({
                        'name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                        f'{symbols_name[name]["description_zh"]}">{name}</span>',
                        'bladed_value': '-' if not symbols_name[name]['bladed'] else
                        f'<input type="text" class="table-value text-primary" id="{name}-bladed" disabled value="{bladed.query(symbols_name[name]["bladed"])[1]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                        'symbol_value': '-' if name in only_in_bladed else
                        f'<input type="text" class="table-value text-primary" id="{name}-symbol" disabled value="{value}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                        'description': symbols_name[name]["description_zh"]
                    })
                if 'T_' in name:
                    for index in value.index:
                        symbols_value['schedules'].append({
                            'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                            f'{symbols_name[name]["description_zh"]}">{name}</span>',
                            'Enabled':
                                f'<input type="text" class="table-value enable-col  text-danger" id="{name}{index}-Enabled" disabled value="{value.at[0, "Enabled"]}"'
                                f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                            'Display_Name': '-',
                            '0': '-' if '_0' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-0" disabled value="{value.at[index, "_0"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '1': '-' if '_1' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-1" disabled value="{value.at[index, "_1"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '2': '-' if '_2' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-2" disabled value="{value.at[index, "_2"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '3': '-' if '_3' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-3" disabled value="{value.at[index, "_3"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '4': '-' if '_4' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-4" disabled value="{value.at[index, "_4"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '5': '-' if '_5' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-5" disabled value="{value.at[index, "_5"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '6': '-' if '_6' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-6" disabled value="{value.at[index, "_6"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '7': '-' if '_7' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-7" disabled value="{value.at[index, "_7"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '8': '-' if '_8' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-8" disabled value="{value.at[index, "_8"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '9': '-' if '_9' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-9" disabled value="{value.at[index, "_9"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">'
                        })
                if 'F_' in name:
                    for index in value.index:
                        symbols_value['filters'].append({
                            'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                            f'{symbols_name[name]["description_zh"]}">{name}</span>',
                            'Enabled':
                            f'<input type="text" class="table-value enable-col text-danger" id="{name}{index}-Enabled" disabled value="{value.at[index, "Enabled"]}"'
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
                            f'<input type="text" class="table-value frequency-col text-primary" id="{name}{index}-Numerator_Frequency" disabled value="{value.at[index, "Numerator_Frequency"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'Numerator_Damping_Ratio':
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-Numerator_Damping_Ratio" disabled value="{value.at[index, "Numerator_Damping_Ratio"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'Denominator_Frequency':
                            f'<input type="text" class="table-value frequency-col text-primary" id="{name}{index}-Denominator_Frequency" disabled value="{value.at[index, "Denominator_Frequency"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'Denominator_Damping_Ratio':
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-Denominator_Damping_Ratio" disabled value="{value.at[index, "Denominator_Damping_Ratio"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'W0':
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-W0" disabled value="{value.at[index, "W0"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'Prewarping_Wc':
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-Prewarping_Wc" disabled value="{value.at[index, "Prewarping_Wc"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                        })

    return jsonify(symbols_value)


@task.route('write/<taskname>/<obj>', methods=['GET', 'POST'])
@login_required
def set_value(taskname, obj):
    user = load_user(current_user.get_id())
    dest = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), user.username, taskname)
    _task = Task.query.filter_by(name=taskname).first()
    data = request.json['data']
    target = request.json['target']

    bladed_data = {k.split('-')[0]: v.strip() for k, v in data.items() if '-bladed' in k}
    symbol_data = {k: v.strip() for k, v in data.items() if '-bladed' not in k}

    if bladed_data:
        with current_app.open_instance_resource('name_mapping.json') as f:
            symbols_name = OrderedDict(json.load(f))

        bladed = Bladed(os.path.join(dest, _task.bladed_filename))
        bladed_args = {symbols_name[k]['bladed']: v for k, v in bladed_data.items()}
        bladed.set(**bladed_args)

    if symbol_data and obj == 'symbol':
        db_symbol_path = os.path.join(dest, taskname + '.db')
        db_symbol = SymbolDB()
        db_symbol.load_db(db_symbol_path, excel_name=_task.symbol_filename)
        db_symbol.connect()
        db_symbol.update(target, **symbol_data)
        db_symbol.close()

    if symbol_data and obj == 'xml':
        xml_path = os.path.join(dest, _task.xml_filename)
        xml = XML()
        try:
            xml.open(xml_path)
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

    return initial_value(taskname, obj)


@task.route('search/<taskname>/<obj>', methods=['POST'])
@login_required
def search_list(taskname, obj):
    user = load_user(current_user.get_id())
    dest = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), user.username, taskname)
    _task = Task.query.filter_by(name=taskname).first()

    key_word = request.json.strip()
    names = []

    if key_word and obj == 'symbol':
        db_symbol_path = os.path.join(dest, taskname + '.db')
        db_symbol = SymbolDB()
        db_symbol.load_db(db_symbol_path)
        db_symbol.connect()
        result = db_symbol.query(key_word.replace('_', '/_'))
        names = [r[0] for r in result]
        db_symbol.close()
    if key_word and obj == 'xml':
        xml_path = os.path.join(dest, _task.xml_filename)
        xml = XML()
        try:
            xml.open(xml_path)
        except FileNotFoundError:
            return None

        names = xml.query(key_word, name_only=True)

    return jsonify(names)


@task.route('search/<taskname>/<obj>/<param>', methods=['POST'])
@login_required
def search(taskname, obj, param):
    user = load_user(current_user.get_id())
    dest = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), user.username, taskname)

    _task = Task.query.filter_by(name=taskname).first()

    symbols_value = {'params': [], 'filters': [], 'schedules': []}

    if obj == "symbol":
        db_symbol_path = os.path.join(dest, taskname + '.db')
        db_symbol = SymbolDB()
        db_symbol.load_db(db_symbol_path)
        db_symbol.connect()

        p_queried = {} if param[:2] in ['F_', 'T_'] else db_symbol.multi_query([param])
        f_queried = {} if 'F_' not in param else db_symbol.multi_query([param])
        t_queried = {} if 'T_' not in param else db_symbol.multi_query([param])
        db_symbol.close()

        if task is not None:
            pattern = re.compile(r'\d+$')
            # 保证显示顺序
            symbols_value['params'] = [{
                'name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{value.at["Description_en_GB"]}">{name}</span>',
                'bladed_value': '-',
                'symbol_value': f'<input type="text" class="table-value text-primary" id="{name}-symbol" '
                f'disabled value="{value.at["Initial_Value"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'description': value.at["Description_en_GB"]
                }
                for name, value in p_queried.items()
            ]
            symbols_value['schedules'] = [{
                'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{t_queried[name].at["Description_en_GB"]}">{pattern.sub("", name, 1)}</span>',
                'Enabled':
                f'<input type="text" class="table-value enable-col  text-danger" id="{name}-Enabled" disabled value="{t_queried[name].at["Enabled"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                'Display_Name': t_queried[name].at['Display_Name'],
                '0': '-' if t_queried[name].at['_0'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-0" disabled value="{t_queried[name].at["_0"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '1': '-' if t_queried[name].at['_1'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-1" disabled value="{t_queried[name].at["_1"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '2': '-' if t_queried[name].at['_2'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-2" disabled value="{t_queried[name].at["_2"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '3': '-' if t_queried[name].at['_3'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-3" disabled value="{t_queried[name].at["_3"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '4': '-' if t_queried[name].at['_4'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-4" disabled value="{t_queried[name].at["_4"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '5': '-' if t_queried[name].at['_5'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-5" disabled value="{t_queried[name].at["_5"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '6': '-' if t_queried[name].at['_6'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-6" disabled value="{t_queried[name].at["_6"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '7': '-' if t_queried[name].at['_7'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-7" disabled value="{t_queried[name].at["_7"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '8': '-' if t_queried[name].at['_8'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-8" disabled value="{t_queried[name].at["_8"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '9': '-' if t_queried[name].at['_9'] == 'None' else
                f'<input type="text" class="table-value text-primary" id="{name}-9" disabled value="{t_queried[name].at["_9"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">'
            } for name in t_queried.keys()
            ]
            symbols_value['filters'] = [{
                'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{value.at["Description_en_GB"]}">{pattern.sub("", name, 1)}</span>',
                'Enabled':
                f'<input type="text" class="table-value enable-col  text-danger" id="{name}-Enabled" disabled value="{value.at["Enabled"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                'Display_Name': value.at["Display_Name"],
                'Numerator_Type': value.at["Numerator_Type"],
                'Denominator_Type': value.at["Denominator_Type"],
                'Numerator_TC': value.at["Numerator_TC"],
                # f'<input type="text" class="table-value" disabled value="{f_queried[name].at["Numerator_TC"]}"'
                # f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Denominator_TC': value.at["Denominator_TC"],
                # f'<input type="text" class="table-value" disabled value="{f_queried[name].at["Denominator_TC"]}"'
                # f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Numerator_Frequency':
                f'<input type="text" class="table-value text-primary frequency-col" id="{name}-Numerator_Frequency" disabled value="{value.at["Numerator_Frequency"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Numerator_Damping_Ratio':
                f'<input type="text" class="table-value text-primary" id="{name}-Numerator_Damping_Ratio" disabled value="{value.at["Numerator_Damping_Ratio"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Denominator_Frequency':
                f'<input type="text" class="table-value text-primary frequency-col" id="{name}-Denominator_Frequency" disabled value="{value.at["Denominator_Frequency"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Denominator_Damping_Ratio':
                f'<input type="text" class="table-value text-primary" id="{name}-Denominator_Damping_Ratio" disabled value="{value.at["Denominator_Damping_Ratio"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'W0':
                f'<input type="text" class="table-value text-primary" id="{name}-W0" disabled value="{value.at["W0"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Prewarping_Wc':
                f'<input type="text" class="table-value text-primary" id="{name}-Prewarping_Wc" disabled value="{value.at["Prewarping_Wc"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">'
            } for name, value in f_queried.items()
            ]

    if obj == 'xml':
        xml_path = os.path.join(dest, _task.xml_filename)
        xml = XML()
        try:
            xml.open(xml_path)
        except FileNotFoundError:
            return jsonify(symbols_value)

        xml_values = xml.find(param)

        if task is not None:
            for name, value in xml_values.items():
                if 'P_' in name:
                    symbols_value['params'].append({
                        'name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                        f'{name}">{name}</span>',
                        'bladed_value': '-',
                        'symbol_value':
                        f'<input type="text" class="table-value text-primary" id="{name}-symbol" disabled value="{value}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                        'description': ""
                    })
                if 'T_' in name:
                    for index in value.index:
                        symbols_value['schedules'].append({
                            'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                            f'{name}">{name}</span>',
                            'Enabled':
                                f'<input type="text" class="table-value enable-col  text-danger" id="{name}{index}-Enabled" disabled value="{value.at[0, "Enabled"]}"'
                                f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                            'Display_Name': '-',
                            '0': '-' if '_0' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-0" disabled value="{value.at[index, "_0"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '1': '-' if '_1' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-1" disabled value="{value.at[index, "_1"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '2': '-' if '_2' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-2" disabled value="{value.at[index, "_2"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '3': '-' if '_3' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-3" disabled value="{value.at[index, "_3"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '4': '-' if '_4' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-4" disabled value="{value.at[index, "_4"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '5': '-' if '_5' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-5" disabled value="{value.at[index, "_5"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '6': '-' if '_6' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-6" disabled value="{value.at[index, "_6"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '7': '-' if '_7' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-7" disabled value="{value.at[index, "_7"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '8': '-' if '_8' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-8" disabled value="{value.at[index, "_8"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            '9': '-' if '_9' not in value.columns else
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-9" disabled value="{value.at[index, "_9"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">'
                        })
                if 'F_' in name:
                    for index in value.index:
                        symbols_value['filters'].append({
                            'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                            f'{name}">{name}</span>',
                            'Enabled':
                            f'<input type="text" class="table-value enable-col text-danger" id="{name}{index}-Enabled" disabled value="{value.at[index, "Enabled"]}"'
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
                            f'<input type="text" class="table-value frequency-col text-primary" id="{name}{index}-Numerator_Frequency" disabled value="{value.at[index, "Numerator_Frequency"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'Numerator_Damping_Ratio':
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-Numerator_Damping_Ratio" disabled value="{value.at[index, "Numerator_Damping_Ratio"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'Denominator_Frequency':
                            f'<input type="text" class="table-value frequency-col text-primary" id="{name}{index}-Denominator_Frequency" disabled value="{value.at[index, "Denominator_Frequency"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'Denominator_Damping_Ratio':
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-Denominator_Damping_Ratio" disabled value="{value.at[index, "Denominator_Damping_Ratio"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'W0':
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-W0" disabled value="{value.at[index, "W0"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                            'Prewarping_Wc':
                            f'<input type="text" class="table-value text-primary" id="{name}{index}-Prewarping_Wc" disabled value="{value.at[index, "Prewarping_Wc"]}"'
                            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                        })

    return jsonify(symbols_value)


@task.route('download/<taskname>/<obj>')
@login_required
def download(taskname, obj):
    user = load_user(current_user.get_id())
    _task = Task.query.filter_by(name=taskname).first()

    folder = os.path.join(current_app.config.get(
        'UPLOADS_DEFAULT_DEST'), user.username, taskname)
    if obj == "symbol":
        return send_from_directory(directory=folder, filename=_task.symbol_filename, as_attachment=True)
    if obj == 'xml':
        return send_from_directory(directory=folder, filename=_task.xml_filename, as_attachment=True)

    abort(404)


@task.route('campbell/<taskname>', methods=['GET', 'POST'])
@login_required
def campbell(taskname):
    user = load_user(current_user.get_id())
    tasks_amount = len(Task.query.filter_by(user_id=user.id).all())
    pass

    return render_template('campbell.html', title="线性化", user=user, tasks_amount=tasks_amount)


@task.route('compiling/<taskname>', methods=['GET', 'POST'])
@login_required
def compiling(taskname):
    user = load_user(current_user.get_id())
    tasks_amount = len(Task.query.filter_by(user_id=user.id).all())
    pass

    return render_template('compile.html', title='控制器编译', user=user, tasks_amount=tasks_amount)