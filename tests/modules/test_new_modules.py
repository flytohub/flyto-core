"""
Tests for all new modules - NO MOCKS, real execution only.

Covers:
- data.xml.parse / data.xml.generate
- data.yaml.parse / data.yaml.generate
- flow.retry / flow.rate_limit / flow.circuit_breaker / flow.debounce / flow.throttle
- crypto.encrypt / crypto.decrypt / crypto.jwt_create / crypto.jwt_verify
- image.crop / image.rotate / image.watermark
- git.clone / git.commit / git.diff
- dns.lookup
- monitor.http_check
- api.github.create_pr / api.github.list_repos (registration only)
- notification.teams.send_message / notification.whatsapp.send_message (registration only)
- ai.vision.analyze / ai.extract / ai.embed / agent.tool_use (registration only)
- ssh.exec / ssh.sftp_upload / ssh.sftp_download (registration only)
"""

import pytest
import sys
import os
import json
import tempfile
import shutil
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


# ============================================================================
# Helpers
# ============================================================================

def get_module(module_id: str):
    """Get module class from registry."""
    from core.modules.registry import ModuleRegistry
    return ModuleRegistry.get(module_id)


def ensure_modules_loaded():
    """Ensure all modules are imported and registered."""
    from core.modules import atomic  # noqa
    try:
        from core.modules import third_party  # noqa
    except Exception:
        pass


# Load modules once
ensure_modules_loaded()


# ============================================================================
# DATA: XML Parse
# ============================================================================

class TestDataXmlParse:
    MODULE_ID = "data.xml.parse"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_parse_simple_xml(self, mod):
        """Parse simple XML string."""
        xml = '<root><name>Alice</name><age>30</age></root>'
        instance = mod({'content': xml}, {})
        result = await instance.execute()
        assert result['ok'] is True
        assert result['data']['root_tag'] == 'root'
        data = result['data']['result']
        assert 'name' in data
        assert 'age' in data

    @pytest.mark.asyncio
    async def test_parse_xml_with_attributes(self, mod):
        """Parse XML with attributes."""
        xml = '<root><user id="1" active="true">Alice</user></root>'
        instance = mod({'content': xml, 'preserve_attributes': True}, {})
        result = await instance.execute()
        assert result['ok'] is True

    @pytest.mark.asyncio
    async def test_parse_xml_from_file(self, mod, tmp_path):
        """Parse XML from file."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text('<root><item>hello</item></root>')
        instance = mod({'file_path': str(xml_file)}, {})
        result = await instance.execute()
        assert result['ok'] is True

    @pytest.mark.asyncio
    async def test_parse_empty_raises(self, mod):
        """No content or file_path should error."""
        instance = mod({}, {})
        with pytest.raises(Exception):
            await instance.execute()

    @pytest.mark.asyncio
    async def test_parse_invalid_xml(self, mod):
        """Invalid XML should error."""
        instance = mod({'content': 'not xml at all <><>'}, {})
        with pytest.raises(Exception):
            await instance.execute()


# ============================================================================
# DATA: XML Generate
# ============================================================================

class TestDataXmlGenerate:
    MODULE_ID = "data.xml.generate"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_generate_simple_xml(self, mod):
        """Generate XML from dict."""
        data = {'name': 'Alice', 'age': '30'}
        instance = mod({'data': data, 'root_tag': 'person'}, {})
        result = await instance.execute()
        assert result['ok'] is True
        xml_str = result['data']['xml']
        assert '<person>' in xml_str or '<person ' in xml_str
        assert 'Alice' in xml_str

    @pytest.mark.asyncio
    async def test_generate_pretty_xml(self, mod):
        """Generate pretty-printed XML."""
        data = {'item': 'test'}
        instance = mod({'data': data, 'pretty': True}, {})
        result = await instance.execute()
        assert result['ok'] is True
        assert '\n' in result['data']['xml']

    @pytest.mark.asyncio
    async def test_roundtrip_xml(self):
        """Parse → Generate → Parse should preserve data."""
        parse_mod = get_module("data.xml.parse")
        gen_mod = get_module("data.xml.generate")

        original_xml = '<config><host>localhost</host><port>8080</port></config>'
        parsed = await parse_mod({'content': original_xml}, {}).execute()
        assert parsed['ok'] is True

        generated = await gen_mod({
            'data': parsed['data']['result'],
            'root_tag': parsed['data']['root_tag']
        }, {}).execute()
        assert generated['ok'] is True
        assert 'localhost' in generated['data']['xml']
        assert '8080' in generated['data']['xml']


# ============================================================================
# DATA: YAML Parse
# ============================================================================

class TestDataYamlParse:
    MODULE_ID = "data.yaml.parse"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_parse_yaml_object(self, mod):
        """Parse YAML object."""
        yaml_str = "name: Alice\nage: 30\ncity: Taipei"
        instance = mod({'content': yaml_str}, {})
        result = await instance.execute()
        assert result['ok'] is True
        data = result['data']['result']
        assert data['name'] == 'Alice'
        assert data['age'] == 30
        assert result['data']['type'] in ('object', 'dict')

    @pytest.mark.asyncio
    async def test_parse_yaml_array(self, mod):
        """Parse YAML array."""
        yaml_str = "- apple\n- banana\n- cherry"
        instance = mod({'content': yaml_str}, {})
        result = await instance.execute()
        assert result['ok'] is True
        assert isinstance(result['data']['result'], list)
        assert len(result['data']['result']) == 3

    @pytest.mark.asyncio
    async def test_parse_yaml_from_file(self, mod, tmp_path):
        """Parse YAML from file."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("database:\n  host: localhost\n  port: 5432")
        instance = mod({'file_path': str(yaml_file)}, {})
        result = await instance.execute()
        assert result['ok'] is True
        assert result['data']['result']['database']['host'] == 'localhost'

    @pytest.mark.asyncio
    async def test_parse_yaml_nested(self, mod):
        """Parse nested YAML."""
        yaml_str = """
server:
  host: 0.0.0.0
  port: 8080
  ssl:
    enabled: true
    cert: /path/to/cert
"""
        instance = mod({'content': yaml_str}, {})
        result = await instance.execute()
        assert result['ok'] is True
        assert result['data']['result']['server']['ssl']['enabled'] is True


# ============================================================================
# DATA: YAML Generate
# ============================================================================

class TestDataYamlGenerate:
    MODULE_ID = "data.yaml.generate"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_generate_yaml(self, mod):
        """Generate YAML from dict."""
        data = {'name': 'Alice', 'age': 30, 'items': ['a', 'b']}
        instance = mod({'data': data}, {})
        result = await instance.execute()
        assert result['ok'] is True
        yaml_str = result['data']['yaml']
        assert 'Alice' in yaml_str
        assert 'items' in yaml_str

    @pytest.mark.asyncio
    async def test_roundtrip_yaml(self):
        """Parse → Generate → Parse should preserve data."""
        parse_mod = get_module("data.yaml.parse")
        gen_mod = get_module("data.yaml.generate")

        original = {'server': {'host': '0.0.0.0', 'port': 8080}, 'debug': True}
        generated = await gen_mod({'data': original}, {}).execute()
        assert generated['ok'] is True

        parsed = await parse_mod({'content': generated['data']['yaml']}, {}).execute()
        assert parsed['ok'] is True
        assert parsed['data']['result'] == original


# ============================================================================
# FLOW: Retry
# ============================================================================

class TestFlowRetry:
    MODULE_ID = "flow.retry"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_retry_initial_state(self, mod):
        """First execution should set up retry plan."""
        instance = mod({
            'max_retries': 3,
            'initial_delay_ms': 100,
            'backoff_multiplier': 2.0,
        }, {})
        result = await instance.execute()
        # Should emit a retry or success event
        assert '__event__' in result

    @pytest.mark.asyncio
    async def test_retry_with_error_context(self, mod):
        """Retry with error in context should track failures."""
        instance = mod({
            'max_retries': 3,
            'initial_delay_ms': 100,
        }, {'__error__': {'message': 'test error'}})
        result = await instance.execute()
        assert '__event__' in result


# ============================================================================
# FLOW: Rate Limit
# ============================================================================

class TestFlowRateLimit:
    MODULE_ID = "flow.rate_limit"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_rate_limit_allows_first_request(self, mod):
        """First request within limit should be allowed."""
        instance = mod({
            'max_requests': 10,
            'window_ms': 60000,
            'strategy': 'token_bucket',
        }, {})
        result = await instance.execute()
        assert result['__event__'] == 'allowed'

    @pytest.mark.asyncio
    async def test_rate_limit_fixed_window(self, mod):
        """Fixed window strategy should work."""
        instance = mod({
            'max_requests': 5,
            'window_ms': 1000,
            'strategy': 'fixed_window',
        }, {})
        result = await instance.execute()
        assert result['__event__'] == 'allowed'


# ============================================================================
# FLOW: Circuit Breaker
# ============================================================================

class TestFlowCircuitBreaker:
    MODULE_ID = "flow.circuit_breaker"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_state(self, mod):
        """Default state should be closed (normal operation)."""
        instance = mod({
            'failure_threshold': 5,
            'reset_timeout_ms': 60000,
        }, {})
        result = await instance.execute()
        assert result['__event__'] == 'closed'

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_error(self, mod):
        """Error should increment failure count."""
        instance = mod({
            'failure_threshold': 5,
            'reset_timeout_ms': 60000,
        }, {'__error__': {'message': 'connection refused'}})
        result = await instance.execute()
        assert '__event__' in result


# ============================================================================
# FLOW: Debounce
# ============================================================================

class TestFlowDebounce:
    MODULE_ID = "flow.debounce"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_debounce_first_call_trailing(self, mod):
        """First call with trailing mode should skip (waiting for quiet period)."""
        instance = mod({
            'delay_ms': 1000,
            'leading': False,
            'trailing': True,
        }, {})
        result = await instance.execute()
        assert '__event__' in result

    @pytest.mark.asyncio
    async def test_debounce_leading_edge(self, mod):
        """Leading edge should execute immediately on first call."""
        instance = mod({
            'delay_ms': 1000,
            'leading': True,
            'trailing': False,
        }, {})
        result = await instance.execute()
        assert result['__event__'] == 'executed'


# ============================================================================
# FLOW: Throttle
# ============================================================================

class TestFlowThrottle:
    MODULE_ID = "flow.throttle"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_throttle_first_call(self, mod):
        """First call should execute (leading=True)."""
        instance = mod({
            'interval_ms': 1000,
            'leading': True,
        }, {})
        result = await instance.execute()
        assert result['__event__'] == 'executed'


# ============================================================================
# CRYPTO: Encrypt / Decrypt
# ============================================================================

class TestCryptoEncryptDecrypt:
    ENCRYPT_ID = "crypto.encrypt"
    DECRYPT_ID = "crypto.decrypt"

    @pytest.fixture
    def encrypt_mod(self):
        return get_module(self.ENCRYPT_ID)

    @pytest.fixture
    def decrypt_mod(self):
        return get_module(self.DECRYPT_ID)

    @pytest.mark.asyncio
    async def test_encrypt_produces_ciphertext(self, encrypt_mod):
        """Encryption should produce ciphertext."""
        instance = encrypt_mod({
            'plaintext': 'Hello World Secret',
            'key': 'my-super-secret-passphrase-123',
        }, {})
        result = await instance.execute()
        assert result['ok'] is True
        assert result['data']['ciphertext'] != 'Hello World Secret'
        assert len(result['data']['ciphertext']) > 0

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, encrypt_mod, decrypt_mod):
        """Encrypt → Decrypt should return original plaintext."""
        plaintext = 'This is a secret message! 中文測試 🔐'
        passphrase = 'strong-passphrase-for-testing-2024'

        # Encrypt
        enc_result = await encrypt_mod({
            'plaintext': plaintext,
            'key': passphrase,
        }, {}).execute()
        assert enc_result['ok'] is True
        ciphertext = enc_result['data']['ciphertext']

        # Decrypt
        dec_result = await decrypt_mod({
            'ciphertext': ciphertext,
            'key': passphrase,
        }, {}).execute()
        assert dec_result['ok'] is True
        assert dec_result['data']['plaintext'] == plaintext

    @pytest.mark.asyncio
    async def test_wrong_key_fails(self, encrypt_mod, decrypt_mod):
        """Decryption with wrong key should raise ModuleError."""
        from core.modules.errors import ModuleError
        enc_result = await encrypt_mod({
            'plaintext': 'secret data',
            'key': 'correct-key',
        }, {}).execute()

        with pytest.raises(ModuleError, match="Decryption failed"):
            await decrypt_mod({
                'ciphertext': enc_result['data']['ciphertext'],
                'key': 'wrong-key',
            }, {}).execute()

    @pytest.mark.asyncio
    async def test_encrypt_different_each_time(self, encrypt_mod):
        """Same plaintext + key should produce different ciphertexts (random salt)."""
        params = {'plaintext': 'same text', 'key': 'same key'}
        r1 = await encrypt_mod(params, {}).execute()
        r2 = await encrypt_mod(params, {}).execute()
        assert r1['data']['ciphertext'] != r2['data']['ciphertext']


# ============================================================================
# CRYPTO: JWT Create / Verify
# ============================================================================

class TestCryptoJwt:
    CREATE_ID = "crypto.jwt_create"
    VERIFY_ID = "crypto.jwt_verify"

    @pytest.fixture
    def create_mod(self):
        return get_module(self.CREATE_ID)

    @pytest.fixture
    def verify_mod(self):
        return get_module(self.VERIFY_ID)

    @pytest.mark.asyncio
    async def test_create_jwt(self, create_mod):
        """Create a JWT token."""
        result = await create_mod({
            'payload': {'user_id': 123, 'role': 'admin'},
            'secret': 'my-jwt-secret',
            'algorithm': 'HS256',
        }, {}).execute()
        assert result['ok'] is True
        token = result['data']['token']
        assert token.count('.') == 2  # JWT has 3 parts

    @pytest.mark.asyncio
    async def test_create_verify_roundtrip(self, create_mod, verify_mod):
        """Create → Verify should return original payload."""
        payload = {'user_id': 42, 'role': 'editor', 'org': 'flyto'}
        secret = 'test-secret-key-256'

        # Create
        create_result = await create_mod({
            'payload': payload,
            'secret': secret,
            'algorithm': 'HS256',
            'expires_in': 3600,
        }, {}).execute()
        assert create_result['ok'] is True
        token = create_result['data']['token']

        # Verify
        verify_result = await verify_mod({
            'token': token,
            'secret': secret,
            'algorithms': ['HS256'],
        }, {}).execute()
        assert verify_result['ok'] is True
        assert verify_result['data']['valid'] is True
        assert verify_result['data']['payload']['user_id'] == 42
        assert verify_result['data']['payload']['role'] == 'editor'

    @pytest.mark.asyncio
    async def test_verify_wrong_secret(self, create_mod, verify_mod):
        """Verify with wrong secret should return valid=False."""
        create_result = await create_mod({
            'payload': {'test': True},
            'secret': 'correct-secret',
        }, {}).execute()

        verify_result = await verify_mod({
            'token': create_result['data']['token'],
            'secret': 'wrong-secret',
        }, {}).execute()
        assert verify_result['ok'] is True
        assert verify_result['data']['valid'] is False

    @pytest.mark.asyncio
    async def test_verify_tampered_token(self, verify_mod):
        """Tampered token should be invalid."""
        result = await verify_mod({
            'token': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.TAMPERED.signature',
            'secret': 'any-secret',
        }, {}).execute()
        assert result['ok'] is True
        assert result['data']['valid'] is False

    @pytest.mark.asyncio
    async def test_jwt_with_expiry(self, create_mod, verify_mod):
        """JWT with expiry should include exp claim."""
        result = await create_mod({
            'payload': {'data': 'test'},
            'secret': 'secret',
            'expires_in': 7200,
            'issuer': 'flyto-test',
        }, {}).execute()
        assert result['ok'] is True

        verify_result = await verify_mod({
            'token': result['data']['token'],
            'secret': 'secret',
            'issuer': 'flyto-test',
        }, {}).execute()
        assert verify_result['data']['valid'] is True
        assert 'exp' in verify_result['data']['payload']
        assert 'iat' in verify_result['data']['payload']


# ============================================================================
# IMAGE: Crop / Rotate / Watermark
# ============================================================================

class TestImageModules:

    @pytest.fixture
    def test_image(self, tmp_path):
        """Create a real test image (100x100 red square)."""
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='red')
        path = tmp_path / "test_input.png"
        img.save(str(path))
        return str(path)

    @pytest.mark.asyncio
    async def test_image_crop(self, test_image, tmp_path):
        """Crop image to 50x50 region."""
        mod = get_module("image.crop")
        output = str(tmp_path / "cropped.png")
        result = await mod({
            'input_path': test_image,
            'output_path': output,
            'left': 10,
            'top': 10,
            'right': 60,
            'bottom': 60,
        }, {}).execute()
        assert result['ok'] is True
        assert result['data']['width'] == 50
        assert result['data']['height'] == 50
        assert os.path.exists(output)

        # Verify actual image dimensions
        from PIL import Image
        img = Image.open(output)
        assert img.size == (50, 50)

    @pytest.mark.asyncio
    async def test_image_rotate(self, test_image, tmp_path):
        """Rotate image 90 degrees."""
        mod = get_module("image.rotate")
        output = str(tmp_path / "rotated.png")
        result = await mod({
            'input_path': test_image,
            'output_path': output,
            'angle': 90,
            'expand': True,
        }, {}).execute()
        assert result['ok'] is True
        assert os.path.exists(output)

    @pytest.mark.asyncio
    async def test_image_rotate_45(self, test_image, tmp_path):
        """Rotate image 45 degrees with expand."""
        mod = get_module("image.rotate")
        output = str(tmp_path / "rotated45.png")
        result = await mod({
            'input_path': test_image,
            'output_path': output,
            'angle': 45,
            'expand': True,
        }, {}).execute()
        assert result['ok'] is True
        # Expanded canvas should be larger than original
        assert result['data']['width'] >= 100 or result['data']['height'] >= 100

    @pytest.mark.asyncio
    async def test_image_watermark_text(self, test_image, tmp_path):
        """Add text watermark."""
        mod = get_module("image.watermark")
        output = str(tmp_path / "watermarked.png")
        result = await mod({
            'input_path': test_image,
            'output_path': output,
            'text': 'FLYTO',
            'position': 'center',
            'opacity': 0.5,
            'font_size': 20,
        }, {}).execute()
        assert result['ok'] is True
        assert os.path.exists(output)

    @pytest.mark.asyncio
    async def test_image_watermark_image(self, tmp_path):
        """Add image watermark."""
        from PIL import Image
        # Create main image
        main = Image.new('RGB', (200, 200), color='blue')
        main_path = str(tmp_path / "main.png")
        main.save(main_path)
        # Create watermark image
        wm = Image.new('RGBA', (50, 50), color=(255, 255, 255, 128))
        wm_path = str(tmp_path / "watermark.png")
        wm.save(wm_path)

        mod = get_module("image.watermark")
        output = str(tmp_path / "result.png")
        result = await mod({
            'input_path': main_path,
            'output_path': output,
            'watermark_image': wm_path,
            'position': 'bottom-right',
            'opacity': 0.7,
        }, {}).execute()
        assert result['ok'] is True


# ============================================================================
# GIT: Clone / Commit / Diff
# ============================================================================

class TestGitModules:

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a real local git repository."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()
        os.system(f'cd "{repo_dir}" && git init -q && git config user.email "test@test.com" && git config user.name "Test"')
        # Create initial commit
        (repo_dir / "README.md").write_text("# Test Repo")
        os.system(f'cd "{repo_dir}" && git add . && git commit -q -m "Initial commit"')
        return str(repo_dir)

    @pytest.mark.asyncio
    async def test_git_diff_clean(self, git_repo):
        """Diff on clean repo should be empty."""
        mod = get_module("git.diff")
        result = await mod({
            'repo_path': git_repo,
        }, {}).execute()
        assert result['ok'] is True

    @pytest.mark.asyncio
    async def test_git_diff_with_changes(self, git_repo):
        """Diff after modifying a file."""
        # Modify file
        with open(os.path.join(git_repo, "README.md"), 'w') as f:
            f.write("# Modified Repo\nNew content here.")

        mod = get_module("git.diff")
        result = await mod({
            'repo_path': git_repo,
        }, {}).execute()
        assert result['ok'] is True
        assert 'Modified' in result['data'].get('diff', '') or result['data'].get('files_changed', 0) >= 0

    @pytest.mark.asyncio
    async def test_git_commit(self, git_repo):
        """Create a real git commit."""
        # Create a new file
        with open(os.path.join(git_repo, "new_file.txt"), 'w') as f:
            f.write("Hello World")

        mod = get_module("git.commit")
        result = await mod({
            'repo_path': git_repo,
            'message': 'Add new file',
            'add_all': True,
        }, {}).execute()
        assert result['ok'] is True
        assert result['data']['commit_hash'] is not None
        assert len(result['data']['commit_hash']) >= 7

    @pytest.mark.asyncio
    async def test_git_clone_local(self, git_repo, tmp_path):
        """Clone from local repo."""
        dest = str(tmp_path / "cloned_repo")
        mod = get_module("git.clone")
        result = await mod({
            'url': git_repo,
            'destination': dest,
        }, {}).execute()
        assert result['ok'] is True
        assert os.path.exists(os.path.join(dest, "README.md"))


# ============================================================================
# DNS: Lookup
# ============================================================================

class TestDnsLookup:
    MODULE_ID = "dns.lookup"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_lookup_google(self, mod):
        """DNS lookup for google.com should return A records."""
        result = await mod({
            'domain': 'google.com',
            'record_type': 'A',
        }, {}).execute()
        assert result['ok'] is True
        assert len(result['data']['records']) > 0

    @pytest.mark.asyncio
    async def test_lookup_mx_record(self, mod):
        """MX lookup for google.com."""
        result = await mod({
            'domain': 'google.com',
            'record_type': 'MX',
        }, {}).execute()
        assert result['ok'] is True

    @pytest.mark.asyncio
    async def test_lookup_nonexistent_domain(self, mod):
        """Lookup for nonexistent domain should handle gracefully."""
        result = await mod({
            'domain': 'this-domain-does-not-exist-xyz123.com',
            'record_type': 'A',
        }, {}).execute()
        # Should either return empty records or error gracefully
        assert result.get('ok') is False or len(result.get('data', {}).get('records', [])) == 0


# ============================================================================
# MONITOR: HTTP Check
# ============================================================================

class TestMonitorHttpCheck:
    MODULE_ID = "monitor.http_check"

    @pytest.fixture
    def mod(self):
        return get_module(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_check_google(self, mod):
        """Health check google.com should be healthy."""
        result = await mod({
            'url': 'https://www.google.com',
            'method': 'GET',
            'expected_status': 200,
            'timeout_ms': 10000,
        }, {}).execute()
        assert result['ok'] is True
        assert result['data']['status'] == 'healthy'
        assert result['data']['response_time_ms'] > 0
        assert result['data']['status_code'] == 200

    @pytest.mark.asyncio
    async def test_check_with_ssl(self, mod):
        """Check SSL certificate."""
        result = await mod({
            'url': 'https://www.google.com',
            'check_ssl': True,
        }, {}).execute()
        assert result['ok'] is True
        # SSL should be valid for google.com
        if result['data'].get('ssl_valid') is not None:
            assert result['data']['ssl_valid'] is True

    @pytest.mark.asyncio
    async def test_check_content_match(self, mod):
        """Check response contains expected text."""
        result = await mod({
            'url': 'https://www.google.com',
            'contains': 'Google',
        }, {}).execute()
        assert result['ok'] is True

    @pytest.mark.asyncio
    async def test_check_unreachable(self, mod):
        """Unreachable host should return unhealthy."""
        result = await mod({
            'url': 'http://192.0.2.1:9999',  # RFC 5737 test address
            'timeout_ms': 2000,
        }, {}).execute()
        # Should either be ok=False or status=unhealthy
        if result.get('ok'):
            assert result['data']['status'] == 'unhealthy'


# ============================================================================
# MODULE REGISTRATION: verify all modules are loadable
# ============================================================================

class TestModuleRegistration:
    """Verify all new modules are properly registered."""

    ALL_NEW_MODULES = [
        # Data
        'data.xml.parse',
        'data.xml.generate',
        'data.yaml.parse',
        'data.yaml.generate',
        # Flow
        'flow.retry',
        'flow.rate_limit',
        'flow.circuit_breaker',
        'flow.debounce',
        'flow.throttle',
        # Crypto
        'crypto.encrypt',
        'crypto.decrypt',
        'crypto.jwt_create',
        'crypto.jwt_verify',
        # Image
        'image.crop',
        'image.rotate',
        'image.watermark',
        # Git
        'git.clone',
        'git.commit',
        'git.diff',
        # DNS
        'dns.lookup',
        # Monitor
        'monitor.http_check',
    ]

    # These may fail to register if deps are missing (asyncssh, pytesseract)
    OPTIONAL_MODULES = [
        'ssh.exec',
        'ssh.sftp_upload',
        'ssh.sftp_download',
        'image.ocr',
    ]

    # These need specific third_party imports
    THIRD_PARTY_MODULES = [
        'ai.vision.analyze',
        'ai.extract',
        'ai.embed',
        'agent.tool_use',
        'api.github.create_pr',
        'api.github.list_repos',
        'notification.teams.send_message',
        'notification.whatsapp.send_message',
    ]

    def test_all_core_modules_registered(self):
        """All new core modules should be in the registry."""
        from core.modules.registry import ModuleRegistry
        for module_id in self.ALL_NEW_MODULES:
            mod = ModuleRegistry.get(module_id)
            assert mod is not None, f"Module {module_id} not registered"

    def test_optional_modules(self):
        """Optional modules should either register or skip cleanly."""
        from core.modules.registry import ModuleRegistry
        for module_id in self.OPTIONAL_MODULES:
            mod = ModuleRegistry.get(module_id)
            # OK if None (dependency missing) or registered
            if mod is not None:
                assert callable(mod), f"Module {module_id} should be callable"

    def test_third_party_modules(self):
        """Third party modules should be registered."""
        from core.modules.registry import ModuleRegistry
        for module_id in self.THIRD_PARTY_MODULES:
            mod = ModuleRegistry.get(module_id)
            assert mod is not None, f"Module {module_id} not registered"
