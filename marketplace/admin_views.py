from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import Conversation, Message, User, SupportTicket, Order
import json

def test_view(request):
    from django.http import HttpResponse
    return HttpResponse("Admin chat URLs are working! Current user: " + str(request.user))

@staff_member_required
def admin_chat_view(request, conversation_id):
    """Display chat interface in admin panel"""
    conversation = get_object_or_404(Conversation, id=conversation_id)
    # Get only real messages with content, not empty system messages
    messages_list = conversation.messages.select_related('sender').filter(
        content__isnull=False
    ).exclude(content__exact='').order_by('timestamp')
    
    context = {
        'conversation': conversation,
        'messages': messages_list,
        'participant1': conversation.participant1,
        'participant2': conversation.participant2,
        'current_moderator': conversation.moderator,
        'can_moderate': request.user.is_staff or request.user.is_superuser,
    }
    
    return render(request, 'admin/marketplace/conversation/chat.html', context)

@staff_member_required
def admin_join_conversation(request, conversation_id):
    """Join conversation as moderator from admin panel"""
    conversation = get_object_or_404(Conversation, id=conversation_id)
    
    if conversation.moderator and conversation.moderator != request.user:
        messages.warning(request, f"This conversation is already being moderated by {conversation.moderator.username}")
    else:
        # Join as moderator
        conversation.moderator = request.user
        conversation.is_disputed = True
        conversation.save()
        
        # Send system message
        Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=f"🛡️ Admin {request.user.username} has joined this conversation to help resolve the dispute.",
            is_system_message=True
        )
        
        messages.success(request, f"You have joined the conversation as moderator")
    
    return redirect('admin_chat:admin_chat', conversation_id=conversation_id)

@staff_member_required 
def admin_leave_conversation(request, conversation_id):
    """Leave conversation as moderator from admin panel"""
    conversation = get_object_or_404(Conversation, id=conversation_id, moderator=request.user)
    
    # Send farewell message
    Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=f"🛡️ Admin {request.user.username} has left the conversation.",
        is_system_message=True
    )
    
    conversation.moderator = None
    conversation.save()
    
    messages.success(request, "You have left the conversation")
    return redirect('/admin/marketplace/conversation/')

@staff_member_required
def admin_resolve_dispute(request, conversation_id):
    """Mark dispute as resolved from admin panel"""
    conversation = get_object_or_404(Conversation, id=conversation_id)
    
    # Send resolution message
    Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=f"🛡️ Admin {request.user.username} has marked this dispute as resolved. If you have further issues, please create a support ticket.",
        is_system_message=True
    )
    
    conversation.is_disputed = False
    conversation.moderator = None
    conversation.save()
    
    messages.success(request, "Dispute has been resolved")
    return redirect('/admin/marketplace/conversation/')

@staff_member_required
@csrf_exempt
def admin_send_message(request, conversation_id):
    """Send message as admin in conversation"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    try:
        data = json.loads(request.body)
        content = data.get('message', '').strip()
        
        if not content:
            return JsonResponse({'success': False, 'error': 'Message cannot be empty'})
        
        conversation = get_object_or_404(Conversation, id=conversation_id)
        
        # Create message
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content,
            is_system_message=False
        )
        
        return JsonResponse({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'sender': message.sender.username,
                'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'is_system_message': message.is_system_message
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@staff_member_required
def support_dashboard(request):
    """Enhanced support ticket dashboard for admins"""
    
    # Get ticket statistics
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    
    stats = {
        'total_open': SupportTicket.objects.filter(status='OPEN').count(),
        'total_in_progress': SupportTicket.objects.filter(status='IN_PROGRESS').count(),
        'total_closed_today': SupportTicket.objects.filter(status='CLOSED', updated_at__date=today).count(),
        'total_this_week': SupportTicket.objects.filter(created_at__date__gte=week_ago).count(),
    }
    
    # Get category breakdown
    category_stats = SupportTicket.objects.filter(status__in=['OPEN', 'IN_PROGRESS']).values('issue_category').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Get user type breakdown for pending tickets
    user_type_stats = SupportTicket.objects.filter(status__in=['OPEN', 'IN_PROGRESS']).values('user_type').annotate(
        count=Count('id')
    )
    
    # Recent urgent tickets (open > 24 hours)
    urgent_cutoff = timezone.now() - timedelta(hours=24)
    urgent_tickets = SupportTicket.objects.filter(
        status='OPEN', 
        created_at__lt=urgent_cutoff
    ).select_related('user').order_by('created_at')[:10]
    
    # Recent tickets for quick overview
    recent_tickets = SupportTicket.objects.select_related('user').order_by('-created_at')[:20]
    
    # Get order details for tickets with order numbers
    for ticket in recent_tickets:
        if ticket.order_number:
            try:
                # Clean the order number - ensure it has # prefix
                clean_order_id = ticket.order_number.strip()
                if not clean_order_id.startswith('#'):
                    clean_order_id = '#' + clean_order_id
                
                ticket.related_order = Order.objects.filter(order_id=clean_order_id).first()
            except:
                ticket.related_order = None
        else:
            ticket.related_order = None
    
    context = {
        'stats': stats,
        'category_stats': category_stats,
        'user_type_stats': user_type_stats,
        'urgent_tickets': urgent_tickets,
        'recent_tickets': recent_tickets,
        'title': 'Support Dashboard',
    }
    
    return render(request, 'admin/support_dashboard.html', context)