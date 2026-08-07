import io
import re

import qrcode
from django.http import HttpResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from organizations.mixins import OrgAdminRequiredMixin

HEX_COLOR_RE = re.compile(r'^[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$')

DEFAULT_FG = '2563EB'
DEFAULT_BG = 'FFFFFF'


def _clean_hex_color(value, default):
    value = (value or '').lstrip('#')
    return f'#{value}' if HEX_COLOR_RE.match(value) else f'#{default}'


class QRGeneratorView(OrgAdminRequiredMixin, TemplateView):
    template_name = 'qr_generator/generate.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = self.organization
        target_path = reverse('customers:select_service', kwargs={'slug': organization.slug})
        context.update({
            'organization': organization,
            'target_url': self.request.build_absolute_uri(target_path),
            'default_fg': DEFAULT_FG,
            'default_bg': DEFAULT_BG,
        })
        return context


class QRImageView(OrgAdminRequiredMixin, View):
    def get(self, request):
        organization = self.organization
        target_path = reverse('customers:select_service', kwargs={'slug': organization.slug})
        target_url = request.build_absolute_uri(target_path)

        fg_color = _clean_hex_color(request.GET.get('fg'), DEFAULT_FG)
        bg_color = _clean_hex_color(request.GET.get('bg'), DEFAULT_BG)

        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(target_url)
        qr.make(fit=True)
        image = qr.make_image(fill_color=fg_color, back_color=bg_color).convert('RGB')

        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)

        response = HttpResponse(buffer, content_type='image/png')
        if request.GET.get('download'):
            filename = f'{organization.slug}-qr-code.png'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
