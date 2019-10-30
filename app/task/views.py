from flask import Blueprint, jsonify, render_template, request, current_app
from flask_login import current_user, login_required
from sqlalchemy import and_, or_
from app.forms import NewTaskForm, EditTaskForm
from app.models import User, Task, load_user
from app.extend.symbol import excel
from app.extend.bladed import Bladed

import os
import json

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

    return render_template('task_working.html', user=user, obj=obj,
                           taskname=taskname, title=taskname)


@task.route('read/<taskname>')
@login_required
def initial_value(taskname):
    user = load_user(current_user.get_id())
    dest = os.path.join(current_app.config.get(
        'UPLOADED_SYMBOL_DEST'), user.username, taskname)

    _task = Task.query.filter_by(name=taskname).first()
    bladed = Bladed(os.path.join(dest, _task.bladed_filename))
    db_symbol_path = os.path.join(dest, 'symbol.db')
    db_symbol = excel.SymbolDB()
    db_symbol.load_db(db_symbol_path)
    db_symbol.connect()

    with current_app.open_instance_resource('name_mapping.json') as f:
        symbols_name = json.load(f)

    symbols_value = {'params': [], 'filters': None, 'schedules': None}
    if task is not None:
        for name, item in sorted(symbols_name.items()):
            # if item['bladed']:
            #     bladed_value[name] = {
            #         'value': Bladed(os.path.join(dest, _task.bladed_filename)).query(item['bladed'])[1],
            #         'desc_zh': item['description_zh']}

            if 'P_' in name:
                only_in_bladed = ['P_DMGT']
                symbols_value['params'].append({
                    'name': name,
                    'desc_zh': item['description_zh'],
                    'bladed_value': '-' if not item['bladed'] else bladed.query(item['bladed'])[1],
                    'symbol_value': '-' if name in only_in_bladed else
                    db_symbol.query(name, db_symbol.belong_to(name))[name].at['Initial_Value']
                })
            # if 'T_' in name:
            #     symbols_value[name] = {
            #         'value': db_symbol.query(name, db_symbol.belong_to(name))[name],
            #         'desc_zh': item['description_zh']}

    return jsonify(symbols_value)
