"""
Flask API 보안 테스트 (S1~S10)
- Path Traversal 차단
- mode 검증
- save-tags 입력 검증
- 에러 내부정보 미포함
"""
import os
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

    def test_s9_empty_dict_accepted(self, client):
        """S9: 모든 태그 삭제 상태도 정상 저장"""
        resp = client.post(
            '/api/save-tags',
            data=json.dumps({}),
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


@pytest.mark.security
class TestCreatorProfileAccess:
    """S11~S13: 제작자 프로필 API 는 vault 밖을 읽지 않는다.

    이 API 는 vault 의 파일을 연다. 경로를 클라이언트가 주지 않고 `account_id` 로
    간접 조회하는 것이 1차 방어이고, `realpath` prefix 검사가 2차다.
    계획: _docs/20260910_01 (W3 T3-a)
    """

    def test_s11_requires_account_id(self, client):
        """S11: account_id 없이 부르면 400"""
        resp = client.get('/api/creator-profile')
        assert resp.status_code == 400

    def test_s12_traversal_account_id_is_not_a_path(self, client):
        """S12: 경로처럼 생긴 account_id 로 파일을 읽지 못한다"""
        for probe in (
            '../../../../.env',
            '..%2F..%2Fetc%2Fpasswd',
            'C:/Users/ahnbu/.env',
            '/etc/passwd',
        ):
            resp = client.get('/api/creator-profile', query_string={'account_id': probe})
            assert resp.status_code == 200
            data = resp.get_json()
            # 계정 목록에 없는 id 이므로 조회 자체가 성립하지 않는다.
            assert data.get('found') is False, probe
            assert 'profile_text' not in data, probe

    def test_s13_no_internal_paths_on_unknown_account(self, client):
        """S13: 없는 계정 응답에 내부 경로가 새지 않는다"""
        resp = client.get('/api/creator-profile', query_string={'account_id': 'nope'})
        body = resp.get_data(as_text=True)
        assert "Traceback" not in body
        assert "\\Users\\" not in body


_FIXTURE_VAULT = os.path.join("tests", "fixtures", "golden", "library", "vault")


@pytest.fixture
def fixture_vault(monkeypatch):
    """운영 볼트 대신 표본 볼트를 읽게 바꿔 끼운다(S11~S13 과 같은 간접 조회 방식)."""
    import scrap_sns_server as server

    monkeypatch.setenv("SNS_LIBRARY_VAULT", os.path.abspath(_FIXTURE_VAULT))
    monkeypatch.setattr(server, "CREATOR_PROFILE_DIR", os.path.abspath(os.path.join(_FIXTURE_VAULT, "_제작자별_상세")))
    return server


@pytest.mark.security
class TestCreatorIdAccess:
    """S14~S17: 제작자 id 경로와 계정 연결 저장. 계획: _docs/20260911_01 (W4 T4-b·T4-d)"""

    def test_s14_traversal_creator_id_rejected(self, client, fixture_vault):
        """S14: 경로처럼 생긴 creator_id 는 400 이다"""
        for probe in ('../../../../.env', '..\\..\\x', 'a/b', '..', '.env', 'C:/Users/ahnbu/.env', ''):
            resp = client.get('/api/creator-profile', query_string={'creator_id': probe})
            assert resp.status_code == 400, probe
            assert 'profile_text' not in resp.get_data(as_text=True), probe

    def test_s15_unknown_creator_is_not_found(self, client, fixture_vault):
        """S15: 목록에 없는 이름은 found:false 이고 내부 경로가 새지 않는다"""
        resp = client.get('/api/creator-profile', query_string={'creator_id': '없는제작자'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['found'] is False and 'profile_text' not in data
        body = resp.get_data(as_text=True)
        assert "\\Users\\" not in body and "Traceback" not in body

    def test_s16_listed_profile_opens(self, client, fixture_vault):
        """S16: 프로필 폴더 목록에 있는 이름만 연다"""
        resp = client.get('/api/creator-profile', query_string={'creator_id': '가나다'})
        data = resp.get_json()
        assert resp.status_code == 200 and data['found'] is True
        assert data['file_name'] == '가나다.md'

    def test_s17_save_creator_links_validates_and_writes(self, client, fixture_vault, tmp_path):
        """S17: 연결 저장 입력 검증 + 원자적 저장"""
        bad = [
            [1, 2],
            {'accounts': []},
            {'accounts': [{'platform': 'facebook', 'key': 'a'}]},
            {'creator_id': '../x', 'accounts': [{'platform': 'threads', 'key': 'a'}]},
            {'source': 'auto', 'accounts': [{'platform': 'threads', 'key': 'a'}]},
        ]
        for payload in bad:
            resp = client.post('/api/save-creator-links', data=json.dumps(payload), content_type='application/json')
            assert resp.status_code == 400, payload
        resp = client.post(
            '/api/save-creator-links',
            data=json.dumps({'name': '표본', 'accounts': [{'platform': 'threads', 'key': 'zz_verify_a'}, {'platform': 'x', 'key': 'zz_verify_b'}]}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.get_json()['creator_id'] == 'link_threads_zz_verify_a'
        saved = json.loads((tmp_path / 'sns_creator_links.json').read_text(encoding='utf-8'))
        assert {(l['platform'], l['key']) for l in saved['links']} == {('threads', 'zz_verify_a'), ('x', 'zz_verify_b')}
