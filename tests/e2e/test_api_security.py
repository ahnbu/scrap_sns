"""
Flask API 보안 테스트 (S1~S10)
- Path Traversal 차단
- mode 검증
- save-tags 입력 검증
- 에러 내부정보 미포함
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.mark.security
class TestPathTraversal:
    """S1~S3: Path Traversal 차단"""

    def test_s1_dot_dot_env(self, client):
        """S1: /../.env.local 접근 차단"""
        resp = client.get('/../.env.local')
        assert resp.status_code in (403, 404)

    def test_s2_auth_file(self, client):
        """S2: /auth/auth_threads.json 접근 차단"""
        resp = client.get('/auth/auth_threads.json')
        assert resp.status_code in (403, 404)

    def test_s3_url_encoded_traversal(self, client):
        """S3: URL 인코딩된 path traversal 차단"""
        resp = client.get('/..%2F..%2Fetc/passwd')
        assert resp.status_code in (403, 404)


@pytest.mark.security
class TestModeValidation:
    """S4~S5: run-scrap mode 검증"""

    def test_s4_invalid_mode(self, client):
        """S4: 무효 mode → 400"""
        resp = client.post(
            '/api/run-scrap',
            data=json.dumps({"mode": "evil"}),
            content_type='application/json'
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid mode" in data.get("message", "")

    def test_s5_valid_mode(self, client):
        """S5: 유효 mode → 400이 아닌 응답 (subprocess를 mock하여 실행 방지)"""
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0
        with patch('subprocess.Popen', return_value=mock_proc):
            resp = client.post(
                '/api/run-scrap',
                data=json.dumps({"mode": "update"}),
                content_type='application/json'
            )
        assert resp.status_code != 400


@pytest.mark.security
class TestSaveTagsValidation:
    """S6~S9: save-tags 입력 검증"""

    def test_s6_array_rejected(self, client):
        """S6: 배열 전송 → 400"""
        resp = client.post(
            '/api/save-tags',
            data=json.dumps([1, 2, 3]),
            content_type='application/json'
        )
        assert resp.status_code == 400

    def test_s7_string_rejected(self, client):
        """S7: 문자열 전송 → 400"""
        resp = client.post(
            '/api/save-tags',
            data=json.dumps("string"),
            content_type='application/json'
        )
        assert resp.status_code == 400

    def test_s8_null_rejected(self, client):
        """S8: null 전송 → 400"""
        resp = client.post(
            '/api/save-tags',
            data='null',
            content_type='application/json'
        )
        assert resp.status_code == 400

    def test_s9_valid_dict_accepted(self, client):
        """S9: 정상 dict → 200, success"""
        resp = client.post(
            '/api/save-tags',
            data=json.dumps({"tag1": {}}),
            content_type='application/json'
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "success"


@pytest.mark.security
class TestErrorInfoLeakage:
    """S10: 에러 응답에 내부 정보 미포함"""

    def test_s10_no_traceback_in_error(self, client):
        """500 응답에 Traceback/프로젝트 경로 미포함"""
        # save-tags에 JSON 파싱 불가능한 데이터 전송 → 에러 유도
        resp = client.post(
            '/api/save-tags',
            data='not-json-at-all',
            content_type='application/json'
        )
        body = resp.get_data(as_text=True)
        assert "Traceback" not in body
        assert "scrap_sns" not in body
        assert "\\Users\\" not in body
