import os
import base64
from urllib.parse import urljoin, urlparse
from flask import Flask, render_template, request, Response, jsonify
import requests
from bs4 import BeautifulSoup
from functools import wraps
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='.', static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB上限

# グローバル設定
TIMEOUT = 30
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# キャッシュ（簡易版）
cache = {}


class ProxyEngine:
    """プロキシエンジン - URL書き換えとリソース処理を管理"""

    def __init__(self, target_url, base_url=None):
        self.target_url = target_url
        self.base_url = base_url or target_url
        self.origin = urlparse(self.base_url).scheme + '://' + urlparse(self.base_url).netloc

    @staticmethod
    def encode_url(url):
        """URLをBase64エンコード"""
        try:
            return base64.b64encode(url.encode()).decode('ascii')
        except Exception:
            return url

    @staticmethod
    def decode_url(encoded_url):
        """Base64エンコードされたURLをデコード"""
        try:
            return base64.b64decode(encoded_url.encode()).decode('utf-8')
        except Exception:
            return encoded_url

    def normalize_url(self, url):
        """相対URLを絶対URLに変換"""
        if not url:
            return ''

        url = url.strip()

        # 既に絶対URLの場合
        if url.startswith('http://') or url.startswith('https://'):
            return url

        # プロトコル相対URL（//で始まる）
        if url.startswith('//'):
            scheme = urlparse(self.base_url).scheme
            return f'{scheme}:{url}'

        # 相対URLを絶対URLに変換
        try:
            return urljoin(self.base_url, url)
        except Exception:
            return url

    def to_proxy_url(self, target_url):
        """URLをプロキシURLに変換"""
        normalized = self.normalize_url(target_url)
        encoded = self.encode_url(normalized)
        return f'/proxy/resource?url={encoded}'

    def rewrite_html(self, html):
        """HTML内の全てのURLをプロキシ経由に書き換え"""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # スクリプトのsrc書き換え
            for script in soup.find_all('script', src=True):
                original_src = script.get('src', '')
                script['src'] = self.to_proxy_url(original_src)

            # リンクのhref書き換え
            for link in soup.find_all('link', href=True):
                original_href = link.get('href', '')
                link['href'] = self.to_proxy_url(original_href)

            # 画像のsrc書き換え
            for img in soup.find_all('img', src=True):
                original_src = img.get('src', '')
                img['src'] = self.to_proxy_url(original_src)

            # 画像のsrcset書き換え
            for img in soup.find_all('img', srcset=True):
                original_srcset = img.get('srcset', '')
                img['srcset'] = self.rewrite_srcset(original_srcset)

            # ピクチャータグのsource
            for source in soup.find_all('source'):
                if source.get('srcset'):
                    source['srcset'] = self.rewrite_srcset(source.get('srcset', ''))
                if source.get('src'):
                    source['src'] = self.to_proxy_url(source.get('src', ''))

            # 動画のsrc書き換え
            for video in soup.find_all('video'):
                if video.get('src'):
                    video['src'] = self.to_proxy_url(video.get('src', ''))
                # video > source
                for source in video.find_all('source'):
                    if source.get('src'):
                        source['src'] = self.to_proxy_url(source.get('src', ''))

            # 音声のsrc書き換え
            for audio in soup.find_all('audio'):
                if audio.get('src'):
                    audio['src'] = self.to_proxy_url(audio.get('src', ''))
                # audio > source
                for source in audio.find_all('source'):
                    if source.get('src'):
                        source['src'] = self.to_proxy_url(source.get('src', ''))

            # フォームのaction書き換え
            for form in soup.find_all('form'):
                if form.get('action'):
                    original_action = form.get('action', '')
                    absolute_action = self.normalize_url(original_action)
                    form['action'] = f'/proxy/form?url={self.encode_url(absolute_action)}'

            # iframeのsrc書き換え
            for iframe in soup.find_all('iframe', src=True):
                original_src = iframe.get('src', '')
                iframe['src'] = self.to_proxy_url(original_src)

            # baseタグを追加（相対URL対応）
            if not soup.find('base'):
                head = soup.find('head')
                if head:
                    base_tag = soup.new_tag('base', href=self.base_url)
                    head.insert(0, base_tag)
                else:
                    body = soup.find('body')
                    if body:
                        base_tag = soup.new_tag('base', href=self.base_url)
                        body.insert(0, base_tag)

            # インラインスタイルのURL書き換え
            for tag in soup.find_all(style=True):
                original_style = tag.get('style', '')
                tag['style'] = self.rewrite_style_urls(original_style)

            # スタイルタグの内容書き換え
            for style_tag in soup.find_all('style'):
                if style_tag.string:
                    style_tag.string = self.rewrite_style_urls(style_tag.string)

            # アンカータグのhref書き換え（外部リンク）
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if href and (href.startswith('http://') or href.startswith('https://')):
                    absolute_url = self.normalize_url(href)
                    a['href'] = f'/proxy/page?url={self.encode_url(absolute_url)}'
                elif href and not href.startswith('#') and not href.startswith('javascript:'):
                    absolute_url = self.normalize_url(href)
                    a['href'] = f'/proxy/page?url={self.encode_url(absolute_url)}'

            return str(soup)
        except Exception as e:
            logger.error(f'HTML rewriting error: {e}')
            return html

    def rewrite_srcset(self, srcset):
        """srcset属性を書き換え"""
        if not srcset:
            return srcset

        parts = []
        for item in srcset.split(','):
            item = item.strip()
            # URLと記述子を分割（例: "image.jpg 1x" または "image.jpg 100w"）
            components = item.rsplit(' ', 1)
            url = components[0]
            descriptor = f' {components[1]}' if len(components) > 1 else ''

            proxied_url = self.to_proxy_url(url)
            parts.append(f'{proxied_url}{descriptor}')

        return ', '.join(parts)

    def rewrite_style_urls(self, css):
        """CSS内のurl()を書き換え"""
        import re

        def replace_url(match):
            url = match.group(1).strip('\'"')
            proxied = self.to_proxy_url(url)
            return f"url('{proxied}')"

        # url('...'), url("..."), url(...)パターンに対応
        return re.sub(r'url\([\'"]?([^\)\'\"]+)[\'"]?\)', replace_url, css)


# Route - Home page
@app.route('/')
def index():
    """Return main page"""
    return render_template('index.html')


# Route - Page proxy
@app.route('/proxy/page')
def proxy_page():
    """Proxy specified URL and return"""
    encoded_url = request.args.get('url', '')

    if not encoded_url:
        return jsonify({'error': 'URL parameter required'}), 400

    try:
        target_url = ProxyEngine.decode_url(encoded_url)

        # URL検証
        parsed = urlparse(target_url)
        if not parsed.scheme or not parsed.netloc:
            return jsonify({'error': 'Invalid URL'}), 400

        # ターゲットサイトからHTMLを取得
        response = requests.get(target_url, headers=REQUEST_HEADERS, timeout=TIMEOUT)
        response.raise_for_status()

        # HTMLであることを確認
        if 'text/html' not in response.headers.get('content-type', ''):
            return jsonify({'error': 'Not HTML content'}), 400

        # HTMLを書き換え
        engine = ProxyEngine(target_url)
        rewritten_html = engine.rewrite_html(response.text)

        return Response(rewritten_html, mimetype='text/html; charset=utf-8')

    except requests.RequestException as e:
        logger.error(f'Request error: {e}')
        return jsonify({'error': f'Failed to fetch URL: {str(e)}'}), 500
    except Exception as e:
        logger.error(f'Proxy error: {e}')
        return jsonify({'error': f'Proxy error: {str(e)}'}), 500


# ルート - リソースプロキシ
@app.route('/proxy/resource')
def proxy_resource():
    """画像、CSS、JSなどのリソースをプロキシで取得"""
    encoded_url = request.args.get('url', '')

    if not encoded_url:
        return jsonify({'error': 'URL parameter required'}), 400

    try:
        target_url = ProxyEngine.decode_url(encoded_url)

        # キャッシュをチェック
        if target_url in cache:
            return cache[target_url]

        # URL検証
        parsed = urlparse(target_url)
        if not parsed.scheme or not parsed.netloc:
            return jsonify({'error': 'Invalid URL'}), 400

        # リソースを取得
        response = requests.get(target_url, headers=REQUEST_HEADERS, timeout=TIMEOUT)
        response.raise_for_status()

        # Content-Typeを保持
        content_type = response.headers.get('content-type', 'application/octet-stream')

        # レスポンスを作成
        result = Response(
            response.content,
            mimetype=content_type,
            headers={
                'Cache-Control': 'public, max-age=86400',
                'Access-Control-Allow-Origin': '*',
            }
        )

        # キャッシュに保存（最大100件）
        if len(cache) < 100:
            cache[target_url] = result

        return result

    except requests.RequestException as e:
        logger.error(f'Resource fetch error: {e}')
        return jsonify({'error': 'Resource not found'}), 404
    except Exception as e:
        logger.error(f'Resource proxy error: {e}')
        return jsonify({'error': 'Resource error'}), 500


# ルート - フォーム送信プロキシ
@app.route('/proxy/form', methods=['GET', 'POST'])
def proxy_form():
    """フォーム送信をプロキシ化"""
    encoded_url = request.args.get('url', '')

    if not encoded_url:
        return jsonify({'error': 'URL parameter required'}), 400

    try:
        target_url = ProxyEngine.decode_url(encoded_url)

        # フォームデータを取得
        data = request.form.to_dict()
        files = request.files.to_dict() if request.files else {}

        # フォーム送信
        response = requests.post(
            target_url,
            data=data,
            files=files,
            headers=REQUEST_HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        # HTML形式の場合は書き換え
        if 'text/html' in response.headers.get('content-type', ''):
            engine = ProxyEngine(target_url)
            rewritten = engine.rewrite_html(response.text)
            return Response(rewritten, mimetype='text/html; charset=utf-8')
        else:
            return Response(response.content, mimetype=response.headers.get('content-type'))

    except Exception as e:
        logger.error(f'Form proxy error: {e}')
        return jsonify({'error': f'Form submission failed: {str(e)}'}), 500


# ルート - API: URLをプロキシ化
@app.route('/api/proxy', methods=['POST'])
def api_proxy():
    """AJAX用APIエンドポイント - URLをプロキシ化"""
    data = request.get_json()
    url = data.get('url', '').strip() if data else ''

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    # https://を付け忘れた場合の対応
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    try:
        # URL検証
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return jsonify({'error': 'Invalid URL format'}), 400

        # ターゲットサイトからHTMLを取得
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=TIMEOUT)
        response.raise_for_status()

        # HTMLであることを確認
        if 'text/html' not in response.headers.get('content-type', ''):
            return jsonify({'error': 'URL is not HTML content'}), 400

        # HTMLを書き換え
        engine = ProxyEngine(url)
        rewritten_html = engine.rewrite_html(response.text)

        return jsonify({
            'success': True,
            'html': rewritten_html,
            'url': url
        })

    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Connection failed - サイトに接続できません'}), 500
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request timeout - リクエストがタイムアウトしました'}), 500
    except requests.exceptions.HTTPError as e:
        return jsonify({'error': f'HTTP Error {e.response.status_code}'}), 500
    except Exception as e:
        logger.error(f'API proxy error: {e}')
        return jsonify({'error': f'Proxy error: {str(e)}'}), 500


# ヘルスチェック
@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
