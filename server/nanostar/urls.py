"""
URL configuration for nanostar project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path,include

urlpatterns = [
    path("admin/", admin.site.urls),
    path('hello/', include('api.urls')),
    
    # 方案 B: 严格按照 RESTful 风格，所有接口和页面都在 /api/ 下
    # 那么前端页面就是 http://127.0.0.1:8000/api/
    # (如果同时使用方案 A 和 B，请保留其中之一，这里推荐用下面的方式给 API 做个命名空间，
    # 但如果为了访客访问方便，上面加上 path('', include('api.urls')) 是最合适的)
    path('api/', include('api.urls')),
]
