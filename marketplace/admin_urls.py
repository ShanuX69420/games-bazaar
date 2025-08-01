from django.urls import path
from . import admin_views

app_name = 'admin_chat'

urlpatterns = [
    path('test/', admin_views.test_view, name='test'),
    path('support-dashboard/', admin_views.support_dashboard, name='support_dashboard'),
    path('conversation/<int:conversation_id>/chat/', admin_views.admin_chat_view, name='admin_chat'),
    path('conversation/<int:conversation_id>/join/', admin_views.admin_join_conversation, name='admin_join_conversation'),
    path('conversation/<int:conversation_id>/leave/', admin_views.admin_leave_conversation, name='admin_leave_conversation'),
    path('conversation/<int:conversation_id>/resolve/', admin_views.admin_resolve_dispute, name='admin_resolve_dispute'),
    path('ajax/admin-send-message/<int:conversation_id>/', admin_views.admin_send_message, name='admin_send_message'),
]