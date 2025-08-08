from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site


class Command(BaseCommand):
    help = 'Update the default site domain and name'

    def handle(self, *args, **options):
        try:
            site = Site.objects.get(pk=1)
            site.domain = 'gamesbazaarpk.com'
            site.name = 'Games Bazaar'
            site.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully updated site to: {site.domain} ({site.name})'
                )
            )
        except Site.DoesNotExist:
            site = Site.objects.create(
                pk=1,
                domain='gamesbazaarpk.com',
                name='Games Bazaar'
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created site: {site.domain} ({site.name})'
                )
            )