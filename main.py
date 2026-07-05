import os
import sys
import base64
from urllib.parse import urljoin, urlparse
from flask import Flask, render_template_string, request, Response, jsonify
import requests
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

TIMEOUT = 30
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

cache = {}

# HTMLテンプレート（インラインで定義）
INDEX_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Web Proxy</title>
    <style>
        @import url('https://rsms.me/inter/inter.css');

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        html, body {
            width: 100%;
            height: 100%;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0a0e27;
            color: #e4e6eb;
            overflow: hidden;
        }

        .container {
            display: flex;
            height: 100vh;
            gap: 0;
        }

        .input-panel {
            width: 420px;
            background: rgba(20, 25, 50, 0.8);
            backdrop-filter: blur(20px);
            border-right: 1px solid rgba(255, 255, 255, 0.08);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            border-radius: 0;
        }

        .input-header {
            padding: 2rem 1.75rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }

        .input-header h2 {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #00d4ff 0%, #0099ff 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .input-header p {
            font-size: 0.85rem;
            color: #8a91a8;
            line-height: 1.5;
        }

        .input-body {
            flex: 1;
            padding: 1.75rem;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
        }

        .input-body::-webkit-scrollbar {
            width: 6px;
        }

        .input-body::-webkit-scrollbar-track {
            background: transparent;
        }

        .input-body::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }

        .form {
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 0.625rem;
        }

        .form-group label {
            font-weight: 500;
            color: #d0d5e0;
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .input-wrapper {
            display: flex;
            gap: 0.625rem;
        }

        input[type="text"] {
            flex: 1;
            padding: 0.875rem 1rem;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #e4e6eb;
            font-size: 0.95rem;
            font-family: inherit;
            transition: all 0.3s ease;
        }

        input[type="text"]::placeholder {
            color: #6b7280;
        }

        input[type="text"]:focus {
            outline: none;
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(0, 212, 255, 0.3);
            box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.1);
        }

        input[type="text"]:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .submit-btn {
            padding: 0.875rem 1.25rem;
            background: linear-gradient(135deg, #00d4ff 0%, #0099ff 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.625rem;
            min-height: 44px;
            white-space: nowrap;
            position: relative;
            overflow: hidden;
        }

        .submit-btn::before {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, transparent 0%, rgba(255, 255, 255, 0.2) 100%);
            opacity: 0;
            transition: opacity 0.3s ease;
        }

        .submit-btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 12px 24px rgba(0, 212, 255, 0.3);
        }

        .submit-btn:hover:not(:disabled)::before {
            opacity: 1;
        }

        .submit-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .spinner {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .status-message {
            padding: 1rem;
            border-radius: 8px;
            font-size: 0.875rem;
            margin-top: 0.75rem;
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .status-message.success {
            background: rgba(34, 197, 94, 0.15);
            color: #86efac;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }

        .status-message.error {
            background: rgba(239, 68, 68, 0.15);
            color: #fca5a5;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .status-message.info {
            background: rgba(59, 130, 246, 0.15);
            color: #93c5fd;
            border: 1px solid rgba(59, 130, 246, 0.3);
        }

        .features {
            margin-top: 1.75rem;
            padding-top: 1.5rem;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
        }

        .features h3 {
            font-size: 0.875rem;
            font-weight: 600;
            color: #d0d5e0;
            margin-bottom: 1rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .feature-list {
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 0.625rem;
        }

        .feature-list li {
            font-size: 0.8125rem;
            color: #9ca3af;
            padding: 0.375rem 0;
            display: flex;
            align-items: flex-start;
            gap: 0.625rem;
            line-height: 1.4;
        }

        .feature-list li::before {
            content: '→';
            color: #00d4ff;
            font-weight: bold;
            flex-shrink: 0;
            margin-top: 2px;
        }

        .preview-panel {
            flex: 1;
            background: linear-gradient(135deg, rgba(10, 14, 39, 0.95) 0%, rgba(20, 25, 50, 0.95) 100%);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            border-left: 1px solid rgba(255, 255, 255, 0.08);
        }

        .preview-header {
            background: rgba(20, 25, 50, 0.5);
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding: 1.25rem 1.75rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .preview-header h2 {
            font-size: 1rem;
            font-weight: 600;
            color: #d0d5e0;
        }

        .preview-actions {
            display: flex;
            gap: 0.5rem;
        }

        .preview-btn {
            padding: 0.5rem 1rem;
            background: rgba(255, 255, 255, 0.08);
            color: #d0d5e0;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.8125rem;
            transition: all 0.2s ease;
            font-weight: 500;
        }

        .preview-btn:hover {
            background: rgba(0, 212, 255, 0.1);
            border-color: rgba(0, 212, 255, 0.3);
            color: #00d4ff;
        }

        .iframe-wrapper {
            flex: 1;
            overflow: hidden;
            position: relative;
            background: rgba(10, 14, 39, 0.5);
        }

        .iframe-wrapper iframe {
            width: 100%;
            height: 100%;
            border: none;
        }

        .empty-state {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #4b5563;
            text-align: center;
            flex-direction: column;
        }

        .empty-icon {
            font-size: 3.5rem;
            display: block;
            margin-bottom: 1rem;
            opacity: 0.6;
        }

        .empty-text {
            font-size: 0.95rem;
            color: #6b7280;
        }

        .current-url {
            word-break: break-all;
            font-size: 0.75rem;
            color: #00d4ff;
            background: rgba(0, 212, 255, 0.08);
            padding: 0.75rem;
            border-radius: 6px;
            margin-top: 0.75rem;
            border: 1px solid rgba(0, 212, 255, 0.2);
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
            line-height: 1.4;
        }

        @media (max-width: 768px) {
            .container {
                flex-direction: column;
            }

            .input-panel {
                width: 100%;
                max-height: 40vh;
                border-right: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }

            .preview-panel {
                border-left: none;
            }
        }

        .hidden {
            display: none !important;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="input-panel">
            <div class="input-header">
                <h2>Web Proxy</h2>
                <p>Access any website through this proxy</p>
            </div>

            <div class="input-body">
                <form class="form" id="proxyForm">
                    <div class="form-group">
                        <label for="urlInput">URL</label>
                        <div class="input-wrapper">
                            <input type="text" id="urlInput" placeholder="example.com" autocomplete="off" autofocus>
                            <button type="submit" class="submit-btn" id="submitBtn">
                                <span>Load</span>
                            </button>
                        </div>
                    </div>
                </form>

                <div id="statusMessage" class="status-message hidden"></div>
                <div id="currentUrl" class="current-url hidden"></div>

                <button id="openNewTabBtn" class="preview-btn" style="width: 100%; margin-top: 1rem; display: none; padding: 0.75rem; background: rgba(0, 212, 255, 0.15); border: 1px solid rgba(0, 212, 255, 0.3); color: #00d4ff;">
                    New Tab
                </button>

                <div class="features">
                    <h3>Features</h3>
                    <ul class="feature-list">
                        <li>All images proxied</li>
                        <li>Video and audio streaming</li>
                        <li>CSS and JavaScript proxied</li>
                        <li>All resources cached</li>
                        <li>Auto link interception</li>
                        <li>Form submission support</li>
                        <li>Complex routing support</li>
                    </ul>
                </div>
            </div>
        </div>

        <div class="preview-panel">
            <div class="preview-header">
                <h2>Preview</h2>
                <div class="preview-actions">
                    <button id="reloadBtn" class="preview-btn" style="display: none;">
                        Reload
                    </button>
                </div>
            </div>

            <div class="iframe-wrapper" id="iframeWrapper">
                <div class="empty-state">
                    <span class="empty-icon">-&gt;</span>
                    <p class="empty-text">Enter a URL to get started</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        const proxyForm = document.getElementById('proxyForm');
        const urlInput = document.getElementById('urlInput');
        const submitBtn = document.getElementById('submitBtn');
        const statusMessage = document.getElementById('statusMessage');
        const currentUrlDiv = document.getElementById('currentUrl');
        const iframeWrapper = document.getElementById('iframeWrapper');
        const openNewTabBtn = document.getElementById('openNewTabBtn');
        const reloadBtn = document.getElementById('reloadBtn');

        let proxiedHtml = '';
        let currentUrl = '';

        proxyForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await handleProxyUrl();
        });

        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                handleProxyUrl();
            }
        });

        async function handleProxyUrl() {
            const url = urlInput.value.trim();

            if (!url) {
                showStatus('Please enter a URL', 'error');
                return;
            }

            let targetUrl = url;
            if (!url.startsWith('http://') && !url.startsWith('https://')) {
                targetUrl = 'https://' + url;
            }

            try {
                new URL(targetUrl);
            } catch {
                showStatus('Invalid URL format', 'error');
                return;
            }

            showStatus('Loading...', 'info');
            submitBtn.disabled = true;

            try {
                const response = await fetch('/api/proxy', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ url: targetUrl }),
                });

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.error || 'Proxy failed');
                }

                const data = await response.json();
                proxiedHtml = data.html;
                currentUrl = data.url;

                displayProxiedContent(proxiedHtml);
                showStatus('Success', 'success');
                currentUrlDiv.textContent = 'Current: ' + currentUrl;
                currentUrlDiv.classList.remove('hidden');

                openNewTabBtn.style.display = 'block';
                reloadBtn.style.display = 'block';

            } catch (error) {
                showStatus('Error: ' + error.message, 'error');
                console.error('Proxy error:', error);
            } finally {
                submitBtn.disabled = false;
            }
        }

        function displayProxiedContent(html) {
            const existingIframe = iframeWrapper.querySelector('iframe');
            if (existingIframe) {
                existingIframe.remove();
            }

            const iframe = document.createElement('iframe');
            iframe.sandbox.add('allow-same-origin', 'allow-scripts', 'allow-forms', 'allow-popups', 'allow-top-navigation');
            iframe.srcdoc = html;

            iframeWrapper.innerHTML = '';
            iframeWrapper.appendChild(iframe);
        }

        function showStatus(message, type) {
            statusMessage.textContent = message;
            statusMessage.className = 'status-message ' + type;
            statusMessage.classList.remove('hidden');

            if (type !== 'error') {
                setTimeout(() => {
                    if (statusMessage.className.includes(type)) {
                        statusMessage.classList.add('hidden');
                    }
                }, 5000);
            }
        }

        openNewTabBtn.addEventListener('click', () => {
            if (proxiedHtml) {
                const blob = new Blob([proxiedHtml], { type: 'text/html; charset=utf-8' });
                const blobUrl = URL.createObjectURL(blob);
                window.open(blobUrl, '_blank');
            }
        });

        reloadBtn.addEventListener('click', () => {
            if (currentUrl) {
                handleProxyUrl();
            }
        });
    </script>
</body>
</html>"""


class ProxyEngine:
    def __init__(self, target_url):
        self.target_url = target_url
        self.origin = urlparse(target_url).scheme + '://' + urlparse(target_url).netloc

    @staticmethod
    def encode_url(url):
        try:
            return base64.b64encode(url.encode()).decode('ascii')
        except Exception:
            return url

    @staticmethod
    def decode_url(encoded_url):
        try:
            return base64.b64decode(encoded_url.encode()).decode('utf-8')
        except Exception:
            return encoded_url

    def normalize_url(self, url):
        if not url:
            return ''

        url = url.strip()

        if url.startswith('http://') or url.startswith('https://'):
            return url

        if url.startswith('//'):
            scheme = urlparse(self.target_url).scheme
            return f'{scheme}:{url}'

        try:
            return urljoin(self.target_url, url)
        except Exception:
            return url

    def to_proxy_url(self, target_url):
        normalized = self.normalize_url(target_url)
        encoded = self.encode_url(normalized)
        return f'/proxy/resource?url={encoded}'

    def rewrite_html(self, html):
        try:
            soup = BeautifulSoup(html, 'html.parser')

            for script in soup.find_all('script', src=True):
                original_src = script.get('src', '')
                script['src'] = self.to_proxy_url(original_src)

            for link in soup.find_all('link', href=True):
                original_href = link.get('href', '')
                link['href'] = self.to_proxy_url(original_href)

            for img in soup.find_all('img', src=True):
                original_src = img.get('src', '')
                img['src'] = self.to_proxy_url(original_src)

            for img in soup.find_all('img', srcset=True):
                original_srcset = img.get('srcset', '')
                img['srcset'] = self.rewrite_srcset(original_srcset)

            for video in soup.find_all('video'):
                if video.get('src'):
                    video['src'] = self.to_proxy_url(video.get('src', ''))
                for source in video.find_all('source'):
                    if source.get('src'):
                        source['src'] = self.to_proxy_url(source.get('src', ''))

            for audio in soup.find_all('audio'):
                if audio.get('src'):
                    audio['src'] = self.to_proxy_url(audio.get('src', ''))
                for source in audio.find_all('source'):
                    if source.get('src'):
                        source['src'] = self.to_proxy_url(source.get('src', ''))

            for form in soup.find_all('form'):
                if form.get('action'):
                    original_action = form.get('action', '')
                    absolute_action = self.normalize_url(original_action)
                    form['action'] = f'/proxy/form?url={self.encode_url(absolute_action)}'

            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if href and (href.startswith('http://') or href.startswith('https://')):
                    absolute_url = self.normalize_url(href)
                    a['href'] = f'/proxy/page?url={self.encode_url(absolute_url)}'

            if not soup.find('base'):
                head = soup.find('head')
                if head:
                    base_tag = soup.new_tag('base', href=self.target_url)
                    head.insert(0, base_tag)

            for tag in soup.find_all(style=True):
                original_style = tag.get('style', '')
                tag['style'] = self.rewrite_style_urls(original_style)

            for style_tag in soup.find_all('style'):
                if style_tag.string:
                    style_tag.string = self.rewrite_style_urls(style_tag.string)

            return str(soup)
        except Exception as e:
            logger.error(f'HTML rewriting error: {e}')
            return html

    def rewrite_srcset(self, srcset):
        if not srcset:
            return srcset

        parts = []
        for item in srcset.split(','):
            item = item.strip()
            components = item.rsplit(' ', 1)
            url = components[0]
            descriptor = f' {components[1]}' if len(components) > 1 else ''
            proxied_url = self.to_proxy_url(url)
            parts.append(f'{proxied_url}{descriptor}')

        return ', '.join(parts)

    def rewrite_style_urls(self, css):
        import re

        def replace_url(match):
            url = match.group(1).strip('\'"')
            proxied = self.to_proxy_url(url)
            return f"url('{proxied}')"

        return re.sub(r'url\([\'"]?([^\)\'\"]+)[\'"]?\)', replace_url, css)


@app.route('/')
def index():
    return render_template_string(INDEX_HTML)


@app.route('/api/proxy', methods=['POST'])
def api_proxy():
    data = request.get_json()
    url = data.get('url', '').strip() if data else ''

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return jsonify({'error': 'Invalid URL format'}), 400

        response = requests.get(url, headers=REQUEST_HEADERS, timeout=TIMEOUT)
        response.raise_for_status()

        if 'text/html' not in response.headers.get('content-type', ''):
            return jsonify({'error': 'URL is not HTML content'}), 400

        engine = ProxyEngine(url)
        rewritten_html = engine.rewrite_html(response.text)

        return jsonify({
            'success': True,
            'html': rewritten_html,
            'url': url
        })

    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Connection failed'}), 500
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request timeout'}), 500
    except requests.exceptions.HTTPError as e:
        return jsonify({'error': f'HTTP Error {e.response.status_code}'}), 500
    except Exception as e:
        logger.error(f'API proxy error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/proxy/resource')
def proxy_resource():
    encoded_url = request.args.get('url', '')

    if not encoded_url:
        return jsonify({'error': 'URL parameter required'}), 400

    try:
        target_url = ProxyEngine.decode_url(encoded_url)

        if target_url in cache:
            return cache[target_url]

        parsed = urlparse(target_url)
        if not parsed.scheme or not parsed.netloc:
            return jsonify({'error': 'Invalid URL'}), 400

        response = requests.get(target_url, headers=REQUEST_HEADERS, timeout=TIMEOUT)
        response.raise_for_status()

        content_type = response.headers.get('content-type', 'application/octet-stream')

        result = Response(
            response.content,
            mimetype=content_type,
            headers={
                'Cache-Control': 'public, max-age=86400',
                'Access-Control-Allow-Origin': '*',
            }
        )

        if len(cache) < 100:
            cache[target_url] = result

        return result

    except Exception as e:
        logger.error(f'Resource proxy error: {e}')
        return jsonify({'error': 'Resource not found'}), 404


@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
