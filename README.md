<!--
 * @Descripttion:
 * @version:
 * @Author: wangshiwen@36719
 * @Date: 2020-01-13 14:38:31
 * @LastEditors: wangshiwen@36719
 * @LastEditTime: 2020-01-13 14:46:54
 -->
## ControlBoard
ControlBoard 是定制化控制业务线上工作平台，目前具备控制器在线整定、Campbell计算、控制器归档及版本管理（托管于BitBucket）、与载荷门户和Jira进行数据交互（外部支持）等特性。

### 部署
1. 安装`requirements.txt`里的依赖包。
2. 设置`./config.py`里面的环境变量。
3. 数据库使用`sqlite3`，存放于`instance`目录。

### 正在开发的功能
- 单工况计算。
- 仿真数据的前端可视化。

### 部署
- 本应用使用Flask框架搭建，最终将部署至FarmInsight作为Django程序的一个子应用。

### 测试地址
~~http://1002dz050490:800/~~

## 本仓库不再更新，已集成到FarmInsight。


