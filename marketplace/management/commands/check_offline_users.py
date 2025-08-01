import asyncio
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async
from marketplace.models import Profile, Conversation


class Command(BaseCommand):
    help = 'Periodically check for users who should be marked offline and broadcast status updates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=60,
            help='Check interval in seconds (default: 60)'
        )

    def handle(self, *args, **options):
        interval = options['interval']
        self.stdout.write(f'Starting offline user checker with {interval}s interval...')
        
        try:
            asyncio.run(self.run_checker(interval))
        except KeyboardInterrupt:
            self.stdout.write('Stopping offline user checker...')

    async def run_checker(self, interval):
        channel_layer = get_channel_layer()
        
        while True:
            try:
                await self.check_and_broadcast_offline_users(channel_layer)
                await asyncio.sleep(interval)
            except Exception as e:
                self.stdout.write(f'Error in checker: {e}')
                await asyncio.sleep(interval)

    async def check_and_broadcast_offline_users(self, channel_layer):
        """Check for users who should be offline and broadcast their status"""
        
        @sync_to_async
        def get_recently_offline_users():
            # Get users who were recently active but should now be offline
            five_minutes_ago = timezone.now() - timedelta(minutes=5)
            six_minutes_ago = timezone.now() - timedelta(minutes=6)
            
            # Users who were active between 5-6 minutes ago (just went offline)
            recently_offline = Profile.objects.filter(
                last_seen__lt=five_minutes_ago,
                last_seen__gte=six_minutes_ago
            ).select_related('user')
            
            return list(recently_offline)
        
        recently_offline_profiles = await get_recently_offline_users()
        
        for profile in recently_offline_profiles:
            await self.broadcast_user_offline(profile.user, channel_layer)
            
        if recently_offline_profiles:
            self.stdout.write(f'Broadcasted offline status for {len(recently_offline_profiles)} users')

    async def broadcast_user_offline(self, user, channel_layer):
        """Broadcast offline status for a specific user to their conversation partners"""
        
        @sync_to_async
        def get_participant_usernames(u):
            # Get conversations where the user is participant1
            p1_convs = Conversation.objects.filter(participant1=u).values_list('participant2__username', flat=True)
            # Get conversations where the user is participant2
            p2_convs = Conversation.objects.filter(participant2=u).values_list('participant1__username', flat=True)
            # Get conversations where the user is a moderator
            mod_convs_p1 = Conversation.objects.filter(moderator=u).values_list('participant1__username', flat=True)
            mod_convs_p2 = Conversation.objects.filter(moderator=u).values_list('participant2__username', flat=True)
            
            # Combine all unique usernames into a set
            all_participants = set(p1_convs) | set(p2_convs) | set(mod_convs_p1) | set(mod_convs_p2)
            
            return all_participants

        # Get the unique set of usernames to notify
        participant_usernames = await get_participant_usernames(user)

        # Broadcast the offline status to each unique participant
        for username in participant_usernames:
            if username != user.username:
                await channel_layer.group_send(
                    f"notifications_{username}",
                    {
                        'type': 'send_notification',
                        'notification_type': 'presence_update',
                        'data': {
                            'username': user.username,
                            'is_online': False,
                            'last_seen_iso': user.profile.last_seen.isoformat() if user.profile.last_seen else None
                        }
                    }
                )