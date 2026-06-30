# server/api/urls.py
from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # 前端页面
    path('', views.index_page, name='index'),

    # 前端交互 API
    path('visitor/verify/', views.verify_visitor_click, name='visitor_verify'),
    path('visitor/comment/', views.add_visitor_comment, name='visitor_comment'),

    # 手机端回调 API
    path('app/action-callback/', views.app_action_callback, name='app_action_callback'),
    path('app/history/', views.get_history, name='history'),
    path('app/report-location/', views.report_location_http, name='report_location'),
]