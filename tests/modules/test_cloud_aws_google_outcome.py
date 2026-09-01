# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the cloud, AWS and Google modules are allowed to claim, and what they must not.

Fourteen modules, three rungs between them, and the tests that matter are the
ones that pin the boundary rather than the happy path:

  * an upload that measured only its own source file stays ACCEPTED however
    large and however successful the transfer looked (`aws.s3.upload`,
    `cloud.gcs.upload`, `cloud.azure.upload`);
  * an upload that read the object back reaches OBSERVED, and drops to
    INDETERMINATE the moment the two lengths disagree (`cloud.aws_s3.upload`);
  * a delete of a key that never existed must not claim more than the 204 it
    got, even though the payload says `deleted: True` (`aws.s3.delete`);
  * an empty listing is ACCEPTED, not OBSERVED, because `count: 0` reads the
    same for an empty bucket and for a prefix that matched nothing
    (`aws.s3.list`, `google.calendar.list_events`, `google.gmail.search`);
  * a send is ACCEPTED however rich the reply is, because a message id is the
    service reporting on its own work (`google.gmail.send`,
    `google.calendar.create_event`).

No sockets and no credentials anywhere: boto3, aioboto3 and azure-storage-blob
are not installed in this environment and are injected as fakes whose only job
is to return the shapes the real SDKs return; google-cloud-storage and aiohttp
are installed and are monkeypatched in place.
"""

import asyncio
import sys
import types
from typing import Any, Dict, List, Optional

import pytest

from core.engine.outcome import (
    ClaimBy,
    Outcome,
    ceiling_for,
    is_on_ladder,
    read_envelope,
)
from core.modules.items import items_to_legacy_context, wrap_legacy_result


# ---------------------------------------------------------------------------
# Reading an answer out of a module result
# ---------------------------------------------------------------------------

def _body(result: Dict[str, Any]) -> Dict[str, Any]:
    """Where the envelope has to live for anything downstream to read it.

    `to_legacy_dict` keeps `{ok, data}` and discards every sibling, so a module
    that returns `data` must put it inside; one that returns a flat dict has its
    fields swept into `data` by `wrap_legacy_result` and may put it at the top.
    Both shapes appear in this group, so the tests read through the same door
    the engine does.
    """
    if isinstance(result.get('data'), dict):
        return result['data']
    return result


def _envelope(result: Dict[str, Any]) -> Dict[str, Any]:
    found = read_envelope(_body(result))
    assert found is not None, f"no well-formed envelope in {sorted(_body(result))}"
    return found


def _rung(result: Dict[str, Any]) -> Outcome:
    return Outcome(_envelope(result)['rung'])


def _effects(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _envelope(result)['effects']


def _kinds(result: Dict[str, Any]) -> List[str]:
    return [effect.get('kind') for effect in _effects(result)]


def _run(coroutine):
    return asyncio.run(coroutine)


# ---------------------------------------------------------------------------
# boto3 -- injected, because it is not installed and must not be
# ---------------------------------------------------------------------------

class FakeS3Client:
    """Only the five calls this group makes, returning the shapes S3 returns."""

    def __init__(
        self,
        *,
        head: Optional[Dict[str, Any]] = None,
        download_bytes: Optional[bytes] = b'0123456789',
        delete_response: Optional[Dict[str, Any]] = None,
        listing: Optional[Dict[str, Any]] = None,
    ):
        self.head_response = {'ContentLength': 10, 'ContentType': 'text/plain'} if head is None else head
        self.download_bytes = download_bytes
        self.delete_response = delete_response if delete_response is not None else {}
        self.listing = listing if listing is not None else {'Contents': [], 'IsTruncated': False}
        self.calls: List[str] = []

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.calls.append('upload_file')
        return None  # what boto3 really returns: nothing at all

    def download_file(self, bucket, key, path):
        self.calls.append('download_file')
        if self.download_bytes is None:
            # The transfer "succeeded" and left no file. Contrived, but it is
            # the shape of any state where the read-back cannot happen.
            return None
        with open(path, 'wb') as handle:
            handle.write(self.download_bytes)

    def head_object(self, Bucket, Key):
        self.calls.append('head_object')
        return dict(self.head_response)

    def delete_object(self, Bucket, Key):
        self.calls.append('delete_object')
        return dict(self.delete_response)

    def list_objects_v2(self, **kwargs):
        self.calls.append('list_objects_v2')
        return dict(self.listing)


@pytest.fixture
def fake_boto3(monkeypatch):
    """`import boto3` inside the modules resolves to a client we control."""
    holder: Dict[str, Any] = {}

    def _install(client: FakeS3Client) -> FakeS3Client:
        module = types.ModuleType('boto3')
        module.client = lambda service, **kwargs: client
        monkeypatch.setitem(sys.modules, 'boto3', module)

        botocore = types.ModuleType('botocore')
        exceptions = types.ModuleType('botocore.exceptions')

        class ClientError(Exception):
            pass

        class BotoCoreError(Exception):
            pass

        exceptions.ClientError = ClientError
        exceptions.BotoCoreError = BotoCoreError
        botocore.exceptions = exceptions
        monkeypatch.setitem(sys.modules, 'botocore', botocore)
        monkeypatch.setitem(sys.modules, 'botocore.exceptions', exceptions)
        holder['client'] = client
        return client

    return _install


AWS_CREDS = {
    'access_key_id': 'AKIAEXAMPLE',
    'secret_access_key': 'secret',
    'region': 'us-east-1',
}


# ---------------------------------------------------------------------------
# aws.s3.upload -- accepted, and it stays there
# ---------------------------------------------------------------------------

class TestAwsS3Upload:
    @pytest.fixture
    def call(self, fake_boto3, sandboxed_tmp_path):
        from core.modules.third_party.cloud.aws import s3_upload as module

        def _call(content: bytes = b'0123456789', client: Optional[FakeS3Client] = None):
            source = sandboxed_tmp_path / 'payload.bin'
            source.write_bytes(content)
            fake_boto3(client or FakeS3Client())
            params = {'bucket': 'b', 'key': 'k', 'file_path': str(source), **AWS_CREDS}
            return _run(module.aws_s3_upload.__wrapped_func__({'params': params}))

        return _call

    def test_a_finished_upload_claims_accepted(self, call):
        """boto3 returning None is the peer acknowledging the bytes -- no more."""
        assert _rung(call()) is Outcome.ACCEPTED

    def test_a_large_successful_upload_is_still_only_accepted(self, call):
        """The rung must not drift with the size of the thing uploaded.

        Nothing about a bigger file is a better observation: the same single
        fact -- the SDK did not raise -- is all that was measured either way.
        """
        assert _rung(call(content=b'x' * 100_000)) is Outcome.ACCEPTED

    def test_the_reported_size_is_named_as_offered_not_stored(self, call):
        result = call(content=b'abcd')
        offered = _effects(result)[0]

        assert offered['kind'] == 'object_bytes_offered'
        assert offered['bytes_offered'] == 4
        assert 'getsize' in offered['measured_by']
        assert _body(result)['size'] == 4

    def test_the_missing_read_back_is_recorded_rather_than_omitted(self, call):
        gap = _effects(call())[1]

        assert gap['kind'] == 'object_not_read_back'
        assert gap['measured_by'] is None

    def test_nobody_claimed_an_expectation(self, call):
        assert _envelope(call())['claim_by'] == ClaimBy.NONE.value

    def test_no_postcondition_and_no_evidence_ref(self, call):
        found = _envelope(call())
        assert found['postcondition'] is None
        assert found['evidence_ref'] is None


# ---------------------------------------------------------------------------
# aws.s3.download -- the read-back decides
# ---------------------------------------------------------------------------

class TestAwsS3Download:
    @pytest.fixture
    def call(self, fake_boto3, sandboxed_tmp_path):
        from core.modules.third_party.cloud.aws import s3_download as module

        def _call(client: FakeS3Client):
            fake_boto3(client)
            destination = sandboxed_tmp_path / 'out' / 'file.bin'
            params = {
                'bucket': 'b', 'key': 'k',
                'output_path': str(destination),
                **AWS_CREDS,
            }
            return _run(module.aws_s3_download.__wrapped_func__({'params': params}))

        return _call

    def test_a_file_of_the_reported_length_is_observed(self, call):
        result = call(FakeS3Client(download_bytes=b'0123456789',
                                   head={'ContentLength': 10, 'ContentType': 'text/plain'}))

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['bytes_on_disk'] == 10

    def test_the_observation_is_attributed_to_this_module(self, call):
        """INFERRED: the equality is this module's predicate, not a caller's."""
        result = call(FakeS3Client(download_bytes=b'0123456789'))
        assert _envelope(result)['claim_by'] == ClaimBy.INFERRED.value

    def test_a_short_file_is_indeterminate_not_failed(self, call):
        """Nobody declared a size contract, so a disagreement is "we cannot say".

        FAILED would mean a postcondition somebody asked for was evaluated and
        broke. There is none: the comparison is ours, and head_object is a
        second request that an overwrite can move under our feet.
        """
        result = call(FakeS3Client(download_bytes=b'012', head={'ContentLength': 10}))

        assert _rung(result) is Outcome.INDETERMINATE
        assert not is_on_ladder(_rung(result))
        assert 'object_length_disagrees' in _kinds(result)

    def test_no_reported_length_falls_back_to_accepted(self, call):
        """A missing ContentLength leaves nothing to compare -- not a zero."""
        result = call(FakeS3Client(download_bytes=b'0123456789', head={}))

        assert _rung(result) is Outcome.ACCEPTED
        assert 'local_file_not_observed' in _kinds(result)

    def test_a_file_that_cannot_be_stat_ed_falls_back_to_accepted(self, call):
        """Losing the ability to look is not the same as the transfer failing."""
        result = call(FakeS3Client(download_bytes=None))

        assert _rung(result) is Outcome.ACCEPTED
        assert _body(result)['bytes_on_disk'] is None

    def test_the_remote_length_is_never_mistaken_for_the_local_one(self, call):
        result = call(FakeS3Client(download_bytes=b'0123456789'))
        remote = _effects(result)[0]

        assert remote['kind'] == 'object_length_reported'
        assert 'head_object' in remote['measured_by']


# ---------------------------------------------------------------------------
# aws.s3.delete -- a 204 for a key that was never there
# ---------------------------------------------------------------------------

class TestAwsS3Delete:
    @pytest.fixture
    def call(self, fake_boto3):
        from core.modules.third_party.cloud.aws import s3_delete as module

        def _call(client: Optional[FakeS3Client] = None):
            fake_boto3(client or FakeS3Client())
            params = {'bucket': 'b', 'key': 'k', **AWS_CREDS}
            return _run(module.aws_s3_delete.__wrapped_func__({'params': params}))

        return _call

    def test_a_delete_claims_accepted(self, call):
        assert _rung(call()) is Outcome.ACCEPTED

    def test_deleting_a_key_that_never_existed_claims_exactly_the_same(self, call):
        """The whole reason this cannot be OBSERVED.

        S3 answers 204 either way, so the module's own `deleted: True` is the
        same literal in both runs. A rung that moved between them would be
        reading something the code never had.
        """
        missing_key = call(FakeS3Client(delete_response={}))
        real_object = call(FakeS3Client(delete_response={'VersionId': 'v1'}))

        assert _rung(missing_key) is _rung(real_object) is Outcome.ACCEPTED
        assert _body(missing_key)['deleted'] is True
        assert _body(real_object)['deleted'] is True

    def test_the_version_id_travels_as_the_peers_own_report(self, call):
        effect = _effects(call(FakeS3Client(delete_response={'VersionId': 'v1', 'DeleteMarker': True})))[0]

        assert effect['version_id'] == 'v1'
        assert effect['delete_marker'] is True
        assert 'without raising' in effect['measured_by']


# ---------------------------------------------------------------------------
# aws.s3.list -- rows returned, or nothing returned
# ---------------------------------------------------------------------------

class TestAwsS3List:
    @pytest.fixture
    def call(self, fake_boto3):
        from core.modules.third_party.cloud.aws import s3_list as module

        def _call(listing: Dict[str, Any]):
            fake_boto3(FakeS3Client(listing=listing))
            params = {'bucket': 'b', 'prefix': 'p/', **AWS_CREDS}
            return _run(module.aws_s3_list.__wrapped_func__({'params': params}))

        return _call

    def test_objects_that_came_back_are_observed(self, call):
        result = call({'Contents': [{'Key': 'p/a', 'Size': 3}], 'IsTruncated': False})

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['count'] == 1

    def test_an_empty_listing_is_accepted_not_observed(self, call):
        """`count: 0` for an empty bucket and for a wrong prefix are one value.

        The same shape as `database.query`'s empty result set, and it gets the
        same answer: the service replied, and the reply observed nothing.
        """
        result = call({'Contents': [], 'IsTruncated': False})

        assert _rung(result) is Outcome.ACCEPTED
        assert _body(result)['count'] == 0
        assert 'no_objects_returned' in _kinds(result)

    def test_truncation_is_carried_so_the_count_is_not_read_as_a_total(self, call):
        result = call({'Contents': [{'Key': 'p/a', 'Size': 3}], 'IsTruncated': True})

        assert _effects(result)[0]['truncated'] is True


# ---------------------------------------------------------------------------
# aioboto3 -- injected for cloud.aws_s3.*
# ---------------------------------------------------------------------------

class _FakeBody:
    def __init__(self, payload: bytes):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self):
        return self._payload


class FakeAsyncS3:
    def __init__(
        self,
        *,
        head: Optional[Dict[str, Any]] = None,
        download_bytes: Optional[bytes] = b'0123456789',
        get_object: Optional[Dict[str, Any]] = None,
    ):
        self.head_response = {'ETag': '"abc"', 'ContentLength': 10} if head is None else head
        self.download_bytes = download_bytes
        self.get_object_response = get_object

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def upload_file(self, filename, bucket, key, ExtraArgs=None):
        return None

    async def put_object(self, Bucket, Key, Body, **kwargs):
        return {'ETag': '"abc"'}

    async def download_file(self, bucket, key, path):
        if self.download_bytes is None:
            return None
        with open(path, 'wb') as handle:
            handle.write(self.download_bytes)

    async def head_object(self, Bucket, Key):
        return dict(self.head_response)

    async def get_object(self, Bucket, Key):
        return dict(self.get_object_response or {})


@pytest.fixture
def fake_aioboto3(monkeypatch):
    def _install(s3: FakeAsyncS3):
        module = types.ModuleType('aioboto3')

        class Session:
            def __init__(self, **kwargs):
                pass

            def client(self, service):
                return s3

        module.Session = Session
        monkeypatch.setitem(sys.modules, 'aioboto3', module)
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIAEXAMPLE')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        return s3

    return _install


class TestCloudAwsS3Upload:
    """The one upload in this group that reads the object back."""

    @pytest.fixture
    def call(self, fake_aioboto3, sandboxed_tmp_path):
        from core.modules.third_party.cloud import storage as module

        def _call(s3: FakeAsyncS3, *, content: Optional[str] = None, file_bytes: bytes = b'0123456789'):
            fake_aioboto3(s3)
            params: Dict[str, Any] = {'bucket': 'b', 'key': 'k'}
            if content is None:
                source = sandboxed_tmp_path / 'payload.bin'
                source.write_bytes(file_bytes)
                params['file_path'] = str(source)
            else:
                params['content'] = content
            return _run(module.aws_s3_upload.__wrapped_func__({'params': params}))

        return _call

    def test_an_object_that_reads_back_at_the_offered_length_is_observed(self, call):
        result = call(FakeAsyncS3(head={'ETag': '"abc"', 'ContentLength': 10}))

        assert _rung(result) is Outcome.OBSERVED
        assert _envelope(result)['claim_by'] == ClaimBy.INFERRED.value
        assert _body(result)['bytes_in_store'] == 10

    def test_the_content_branch_measures_the_encoded_body(self, call):
        result = call(FakeAsyncS3(head={'ContentLength': 5}), content='hello')

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['bytes_offered'] == 5

    def test_a_disagreeing_length_is_indeterminate(self, call):
        """A stale object of another size at the same key reads exactly so."""
        result = call(FakeAsyncS3(head={'ContentLength': 4096}))

        assert _rung(result) is Outcome.INDETERMINATE
        assert 'object_length_disagrees' in _kinds(result)

    def test_no_content_length_leaves_nothing_to_compare(self, call):
        result = call(FakeAsyncS3(head={'ETag': '"abc"'}))

        assert _rung(result) is Outcome.ACCEPTED
        assert _body(result)['bytes_in_store'] is None

    def test_the_etag_alone_never_lifts_the_rung(self, call):
        """An ETag is the store's name for what it says it holds.

        It is reported and nothing rests on it: the ACCEPTED case above has one
        and stays ACCEPTED.
        """
        result = call(FakeAsyncS3(head={'ETag': '"abc"'}))

        assert _body(result)['etag'] == 'abc'
        assert _rung(result) is Outcome.ACCEPTED


class TestCloudAwsS3Download:
    @pytest.fixture
    def call(self, fake_aioboto3, sandboxed_tmp_path):
        from core.modules.third_party.cloud import storage as module

        def _call(s3: FakeAsyncS3, *, to_file: bool = True):
            fake_aioboto3(s3)
            params: Dict[str, Any] = {'bucket': 'b', 'key': 'k'}
            if to_file:
                params['file_path'] = str(sandboxed_tmp_path / 'saved.bin')
            return _run(module.aws_s3_download.__wrapped_func__({'params': params}))

        return _call

    def test_a_saved_file_of_the_reported_length_is_observed(self, call):
        result = call(FakeAsyncS3(download_bytes=b'0123456789', head={'ContentLength': 10}))

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['bytes_local'] == 10

    def test_a_saved_file_of_another_length_is_indeterminate(self, call):
        result = call(FakeAsyncS3(download_bytes=b'01', head={'ContentLength': 10}))

        assert _rung(result) is Outcome.INDETERMINATE

    def test_a_file_that_was_never_written_falls_back_to_accepted(self, call):
        result = call(FakeAsyncS3(download_bytes=None, head={'ContentLength': 10}))

        assert _rung(result) is Outcome.ACCEPTED
        assert _body(result)['bytes_local'] is None

    def test_an_unmeasured_length_names_no_measurement(self, call):
        """`measured_by` is where a reader looks for the line that measured.

        A failure message parked there would be read as one, so the absence is
        an explicit None and the reason travels beside it.
        """
        effect = _effects(call(FakeAsyncS3(download_bytes=None)))[0]

        assert effect['measured_by'] is None
        assert 'os.stat failed' in effect['reason']

    def test_the_memory_branch_compares_bytes_read_against_the_declared_length(self, call):
        result = call(
            FakeAsyncS3(get_object={'Body': _FakeBody(b'hello'), 'ContentLength': 5}),
            to_file=False,
        )

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['content'] == 'hello'
        assert _body(result)['bytes_local'] == 5

    def test_a_stream_cut_short_is_indeterminate(self, call):
        """The header promised more than the stream delivered."""
        result = call(
            FakeAsyncS3(get_object={'Body': _FakeBody(b'hel'), 'ContentLength': 5}),
            to_file=False,
        )

        assert _rung(result) is Outcome.INDETERMINATE


# ---------------------------------------------------------------------------
# google-cloud-storage -- installed, monkeypatched in place
# ---------------------------------------------------------------------------

class FakeBlob:
    def __init__(self, *, download_bytes: bytes = b'0123456789', reported: Optional[Dict[str, Any]] = None):
        self.download_bytes = download_bytes
        self.content_type = None
        self.public_url = 'https://storage.googleapis.com/b/o'
        self.made_public = False
        defaults = {'size': 10, 'etag': 'e-tag', 'md5_hash': 'm'}
        for key, value in (defaults if reported is None else reported).items():
            setattr(self, key, value)

    def upload_from_filename(self, path):
        self.uploaded_from = path

    def make_public(self):
        self.made_public = True

    def download_to_filename(self, path):
        with open(path, 'wb') as handle:
            handle.write(self.download_bytes)


@pytest.fixture
def fake_gcs(monkeypatch):
    # importorskip, not a bare import: google-cloud-storage is optional and CI
    # does not install it. A fixture that imports it unconditionally turns every
    # test using it into an ERROR on a machine without the extra, which is not
    # the same as a failure and reads as if the code were broken.
    gcs_module = pytest.importorskip(
        "google.cloud.storage", reason="needs the google-cloud-storage extra"
    )

    def _install(blob: FakeBlob) -> FakeBlob:
        class FakeBucket:
            def blob(self, name):
                return blob

        class FakeClient:
            def bucket(self, name):
                return FakeBucket()

        monkeypatch.setattr(gcs_module, 'Client', FakeClient)
        return blob

    return _install


class TestCloudGcsUpload:
    @pytest.fixture
    def call(self, fake_gcs, sandboxed_tmp_path):
        from core.modules.third_party.cloud.gcs import GCSUploadModule

        def _call(blob: Optional[FakeBlob] = None, content: bytes = b'0123456789'):
            fake_gcs(blob or FakeBlob())
            source = sandboxed_tmp_path / 'payload.bin'
            source.write_bytes(content)
            params = {'file_path': str(source), 'bucket': 'b', 'object_name': 'o'}
            # execute() directly, not run(): the wrapper adds a timeout and a
            # retry and contributes nothing to what the module measured.
            return _run(GCSUploadModule(params, {}).execute())

        return _call

    def test_an_upload_claims_accepted(self, call):
        assert _rung(call()) is Outcome.ACCEPTED

    def test_the_services_own_numbers_do_not_lift_the_rung(self, call):
        """blob.size comes from the upload response -- the peer's own account.

        Reporting it is useful; treating it as an observation would be reading
        the peer's report of the peer's work as evidence about the world.
        """
        result = call(FakeBlob(reported={'size': 10, 'etag': 'e-tag'}))
        reported = _effects(result)[1]

        assert reported['kind'] == 'object_reported_by_service'
        assert reported['reported'] == {'size': 10, 'etag': 'e-tag'}
        assert _rung(result) is Outcome.ACCEPTED

    def test_a_blob_that_reports_nothing_still_returns_a_well_formed_envelope(self, call):
        result = call(FakeBlob(reported={}))

        assert _rung(result) is Outcome.ACCEPTED
        assert _effects(result)[1]['reported'] == {}

    def test_the_local_size_is_named_as_offered(self, call):
        result = call(content=b'abc')

        assert _effects(result)[0]['bytes_offered'] == 3
        assert 'getsize' in _effects(result)[0]['measured_by']


class TestCloudGcsDownload:
    @pytest.fixture
    def call(self, fake_gcs, sandboxed_tmp_path):
        from core.modules.third_party.cloud.gcs import GCSDownloadModule

        def _call(payload: bytes):
            fake_gcs(FakeBlob(download_bytes=payload))
            params = {
                'bucket': 'b',
                'object_name': 'o',
                'destination_path': str(sandboxed_tmp_path / 'sub' / 'saved.bin'),
            }
            return _run(GCSDownloadModule(params, {}).execute())

        return _call

    def test_a_non_empty_file_on_this_host_is_observed(self, call):
        result = call(b'0123456789')

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['size'] == 10
        assert 'getsize' in _effects(result)[0]['measured_by']

    def test_a_zero_byte_result_is_accepted_not_observed(self, call):
        """0 reads the same for an empty object and for a write that never was.

        This is the `file.write` trap in download form: a number that would be
        unchanged had the effect not happened is not evidence of it.
        """
        result = call(b'')

        assert _rung(result) is Outcome.ACCEPTED
        assert 'local_file_empty' in _kinds(result)


# ---------------------------------------------------------------------------
# azure-storage-blob -- injected
# ---------------------------------------------------------------------------

class FakeBlobClient:
    def __init__(self, *, download_bytes: bytes = b'0123456789', upload_response: Optional[Dict[str, Any]] = None):
        self.download_bytes = download_bytes
        self.upload_response = upload_response if upload_response is not None else {'etag': '"0x8D"'}
        self.url = 'https://acct.blob.core.windows.net/c/b'

    def upload_blob(self, data, overwrite=False, content_settings=None):
        self.uploaded = data.read() if hasattr(data, 'read') else data
        return dict(self.upload_response)

    def download_blob(self):
        payload = self.download_bytes

        class _Downloader:
            def readall(self):
                return payload

        return _Downloader()


@pytest.fixture
def fake_azure(monkeypatch):
    def _install(blob_client: FakeBlobClient) -> FakeBlobClient:
        blob_module = types.ModuleType('azure.storage.blob')

        class BlobServiceClient:
            @staticmethod
            def from_connection_string(connection_string):
                class _Service:
                    def get_container_client(self, container):
                        class _Container:
                            def get_blob_client(self, name):
                                return blob_client

                        return _Container()

                return _Service()

        class ContentSettings:
            def __init__(self, content_type=None):
                self.content_type = content_type

        blob_module.BlobServiceClient = BlobServiceClient
        blob_module.ContentSettings = ContentSettings

        storage_module = types.ModuleType('azure.storage')
        storage_module.blob = blob_module
        azure_module = types.ModuleType('azure')
        azure_module.storage = storage_module

        monkeypatch.setitem(sys.modules, 'azure', azure_module)
        monkeypatch.setitem(sys.modules, 'azure.storage', storage_module)
        monkeypatch.setitem(sys.modules, 'azure.storage.blob', blob_module)
        return blob_client

    return _install


# No BlobEndpoint and no AccountName, so `enforce_azure_endpoint` has no host to
# check and this test does no DNS. A connection string naming an account would
# put a resolver call in a unit test.
AZURE_CONNECTION_STRING = 'UseDevelopmentStorage=true'


class TestCloudAzureUpload:
    @pytest.fixture
    def call(self, fake_azure, sandboxed_tmp_path):
        from core.modules.third_party.cloud.azure import AzureUploadModule

        def _call(client: Optional[FakeBlobClient] = None, content: bytes = b'0123456789'):
            fake_azure(client or FakeBlobClient())
            source = sandboxed_tmp_path / 'payload.bin'
            source.write_bytes(content)
            params = {
                'file_path': str(source),
                'container': 'c',
                'blob_name': 'b',
                'connection_string': AZURE_CONNECTION_STRING,
            }
            return _run(AzureUploadModule(params, {}).execute())

        return _call

    def test_an_upload_claims_accepted(self, call):
        assert _rung(call()) is Outcome.ACCEPTED

    def test_the_etag_is_captured_rather_than_discarded(self, call):
        """It used to be thrown away, leaving nothing but "no exception"."""
        result = call(FakeBlobClient(upload_response={'etag': '"0x8D"'}))

        assert _body(result)['etag'] == '"0x8D"'
        assert _effects(result)[1]['kind'] == 'blob_reported_by_service'

    def test_an_etag_is_still_only_the_peers_word(self, call):
        assert _rung(call(FakeBlobClient(upload_response={'etag': '"0x8D"'}))) is Outcome.ACCEPTED

    def test_a_response_without_an_etag_still_returns_an_envelope(self, call):
        result = call(FakeBlobClient(upload_response={}))

        assert _rung(result) is Outcome.ACCEPTED
        assert _body(result)['etag'] == ''


class TestCloudAzureDownload:
    @pytest.fixture
    def call(self, fake_azure, sandboxed_tmp_path):
        from core.modules.third_party.cloud.azure import AzureDownloadModule

        def _call(payload: bytes):
            fake_azure(FakeBlobClient(download_bytes=payload))
            params = {
                'container': 'c',
                'blob_name': 'b',
                'destination_path': str(sandboxed_tmp_path / 'sub' / 'saved.bin'),
                'connection_string': AZURE_CONNECTION_STRING,
            }
            return _run(AzureDownloadModule(params, {}).execute())

        return _call

    def test_a_file_the_length_of_the_payload_is_observed(self, call):
        result = call(b'0123456789')

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['size'] == 10
        assert _body(result)['bytes_received'] == 10

    def test_an_empty_blob_still_compares_and_is_observed(self, call):
        """Unlike GCS, both numbers are known here, so zero is a real match.

        This module holds the payload it wrote, so `0 == 0` is a comparison of
        two measurements rather than a bare size that could mean anything.
        """
        assert _rung(call(b'')) is Outcome.OBSERVED

    def test_a_short_write_would_be_indeterminate(self):
        """The decision function, driven directly.

        The write path cannot be made to write fewer bytes than it was given
        without breaking the file API itself, so the branch is exercised where
        it is decided.
        """
        from core.modules.third_party.cloud.azure import _write_back_outcome

        found = _write_back_outcome(
            path='/tmp/x', payload_bytes=10, size_on_disk=3, observation_error=None
        )

        assert found['rung'] == Outcome.INDETERMINATE.value
        assert found['claim_by'] == ClaimBy.INFERRED.value

    def test_an_unreadable_file_falls_back_to_accepted(self):
        from core.modules.third_party.cloud.azure import _write_back_outcome

        found = _write_back_outcome(
            path='/tmp/x', payload_bytes=10, size_on_disk=None,
            observation_error='OSError: gone',
        )

        assert found['rung'] == Outcome.ACCEPTED.value


# ---------------------------------------------------------------------------
# aiohttp -- installed, monkeypatched for the four google modules
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status: int, payload: Any):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload


class FakeSession:
    """`async with ClientSession()` and `async with session.get/post(...)`."""

    def __init__(self, handler):
        self._handler = handler
        self.requests: List[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _respond(self, url, **kwargs):
        self.requests.append(url)
        status, payload = self._handler(url, kwargs)
        return FakeResponse(status, payload)

    def get(self, url, **kwargs):
        return self._respond(url, **kwargs)

    def post(self, url, **kwargs):
        return self._respond(url, **kwargs)


@pytest.fixture
def fake_aiohttp(monkeypatch):
    import aiohttp

    def _install(handler):
        session = FakeSession(handler)
        monkeypatch.setattr(aiohttp, 'ClientSession', lambda *a, **k: session)
        return session

    return _install


class TestGoogleGmailSend:
    @pytest.fixture
    def call(self, fake_aiohttp):
        from core.modules.third_party.cloud.google import gmail_send as module

        def _call(payload: Dict[str, Any]):
            fake_aiohttp(lambda url, kwargs: (200, payload))
            params = {
                'access_token': 'ya29.token',
                'to': 'team@flyto2.com',
                'subject': 's',
                'body': 'b',
            }
            return _run(module.google_gmail_send.__wrapped_func__({'params': params}))

        return _call

    def test_a_200_with_a_message_id_claims_accepted(self, call):
        result = call({'id': 'm1', 'threadId': 't1'})

        assert _rung(result) is Outcome.ACCEPTED
        assert _body(result)['message_id'] == 'm1'

    def test_a_rich_reply_does_not_promote_the_rung(self, call):
        """The reply that most tempts a reader into calling this observed.

        Labels, a thread, a snippet -- all of it is Gmail describing what Gmail
        did. Nothing here reads the mailbox back and nothing observes delivery.
        """
        result = call({
            'id': 'm1', 'threadId': 't1',
            'labelIds': ['SENT'], 'snippet': 'Hello', 'sizeEstimate': 4096,
        })

        assert _rung(result) is Outcome.ACCEPTED

    def test_the_unobserved_delivery_is_recorded_rather_than_left_out(self, call):
        gap = _effects(call({'id': 'm1'}))[1]

        assert gap['kind'] == 'delivery_not_observed'
        assert gap['measured_by'] is None

    def test_the_ceiling_from_no_declared_postcondition_is_observed(self, call):
        """Even the ceiling is a rung above what this claims.

        Nothing is holding this module down but the absence of a read-back.
        """
        assert ceiling_for(_envelope(call({'id': 'm1'}))['postcondition']) is Outcome.OBSERVED


class TestGoogleCalendarCreateEvent:
    @pytest.fixture
    def call(self, fake_aiohttp):
        from core.modules.third_party.cloud.google import calendar_create as module

        def _call(payload: Dict[str, Any]):
            fake_aiohttp(lambda url, kwargs: (200, payload))
            params = {
                'access_token': 'ya29.token',
                'summary': 'Sprint Planning',
                'start_time': '2026-03-01T10:00:00',
                'end_time': '2026-03-01T11:00:00',
            }
            return _run(module.google_calendar_create_event.__wrapped_func__({'params': params}))

        return _call

    def test_a_created_event_claims_accepted(self, call):
        result = call({'id': 'e1', 'summary': 'Sprint Planning', 'status': 'confirmed'})

        assert _rung(result) is Outcome.ACCEPTED
        assert _body(result)['event_id'] == 'e1'

    def test_a_full_event_resource_in_the_reply_does_not_promote_it(self, call):
        """The echo and the calendar row are one claim from one source."""
        result = call({
            'id': 'e1',
            'summary': 'Sprint Planning',
            'status': 'confirmed',
            'htmlLink': 'https://calendar.google.com/event?eid=e1',
            'start': {'dateTime': '2026-03-01T10:00:00Z'},
            'end': {'dateTime': '2026-03-01T11:00:00Z'},
            'etag': '"123"',
        })

        assert _rung(result) is Outcome.ACCEPTED
        assert _effects(result)[0]['status'] == 'confirmed'


class TestGoogleCalendarListEvents:
    @pytest.fixture
    def call(self, fake_aiohttp):
        from core.modules.third_party.cloud.google import calendar_list as module

        def _call(payload: Dict[str, Any]):
            fake_aiohttp(lambda url, kwargs: (200, payload))
            params = {'access_token': 'ya29.token', 'max_results': 5}
            return _run(module.google_calendar_list_events.__wrapped_func__({'params': params}))

        return _call

    def test_events_that_came_back_are_observed(self, call):
        result = call({'items': [{'id': 'e1', 'summary': 'Standup'}]})

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['count'] == 1

    def test_an_empty_window_is_accepted_not_observed(self, call):
        result = call({'items': []})

        assert _rung(result) is Outcome.ACCEPTED
        assert 'no_events_returned' in _kinds(result)

    def test_the_window_travels_so_the_count_is_not_read_as_a_total(self, call):
        effect = _effects(call({'items': [{'id': 'e1'}]}))[0]

        assert effect['window']['max_results'] == 5


class TestGoogleGmailSearch:
    @pytest.fixture
    def call(self, fake_aiohttp):
        from core.modules.third_party.cloud.google import gmail_search as module

        def _call(ids: List[str], *, metadata_status: int = 200):
            def handler(url, kwargs):
                if url.rstrip('/').endswith('/messages'):
                    return 200, {'messages': [{'id': i} for i in ids]}
                message_id = url.rsplit('/', 1)[-1]
                if metadata_status != 200:
                    return metadata_status, {}
                return 200, {
                    'id': message_id,
                    'threadId': 't',
                    'snippet': 'hi',
                    'payload': {'headers': [{'name': 'Subject', 'value': 'S'}]},
                }

            fake_aiohttp(handler)
            params = {'access_token': 'ya29.token', 'query': 'from:x', 'max_results': 5}
            return _run(module.google_gmail_search.__wrapped_func__({'params': params}))

        return _call

    def test_messages_that_came_back_are_observed(self, call):
        result = call(['m1', 'm2'])

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['total'] == 2
        assert _body(result)['matched_ids'] == 2

    def test_an_empty_search_is_accepted_not_observed(self, call):
        result = call([])

        assert _rung(result) is Outcome.ACCEPTED
        assert 'no_messages_matched' in _kinds(result)

    def test_ids_observed_but_undescribed_still_count_as_observed(self, call):
        """The reason the rung is not read off `len(messages)`.

        Three ids came back from the mailbox and every metadata fetch 404-ed, so
        the payload lists nothing. The search still observed three messages; a
        rung taken from the list would have called that an empty read.
        """
        result = call(['m1', 'm2', 'm3'], metadata_status=404)

        assert _rung(result) is Outcome.OBSERVED
        assert _body(result)['total'] == 0
        assert _body(result)['matched_ids'] == 3
        assert 'message_metadata_incomplete' in _kinds(result)

    def test_a_complete_read_carries_no_shortfall_effect(self, call):
        assert 'message_metadata_incomplete' not in _kinds(call(['m1']))


# ---------------------------------------------------------------------------
# What every one of them has to satisfy
# ---------------------------------------------------------------------------

class TestTheContractItself:
    def test_no_module_in_this_group_claims_verified(self):
        """None of the fourteen declares a postcondition, so none may.

        `ceiling_for(None)` caps an undeclared module at OBSERVED, and a claim
        of VERIFIED here would be a category error rather than an overreach:
        there is no predicate it could be about.
        """
        from core.modules import atomic  # noqa: F401
        from core.modules import composite  # noqa: F401
        from core.modules.registry import ModuleRegistry

        metadata = ModuleRegistry.get_all_metadata(filter_by_stability=False)
        mine = [
            module_id for module_id in metadata
            if module_id.split('.')[0] in ('aws', 'cloud', 'google')
        ]
        assert mine, 'the group is empty -- the ids moved'
        for module_id in mine:
            assert not metadata[module_id].get('postcondition'), module_id

    def test_the_envelope_survives_the_trip_out_of_a_step(self, fake_boto3):
        """The trap this whole contract is shaped around.

        `to_legacy_dict` returns exactly {ok, data} and discards every sibling,
        so an envelope written next to `data` instead of inside it reaches no
        consumer at all. This group has both shapes -- `{ok, data}` from the
        aws.* modules and a flat dict from `cloud.aws_s3.*` -- and both have to
        arrive.
        """
        from core.modules.third_party.cloud.aws import s3_list as module

        fake_boto3(FakeS3Client(listing={'Contents': [{'Key': 'a', 'Size': 1}], 'IsTruncated': False}))
        result = _run(module.aws_s3_list.__wrapped_func__({
            'params': {'bucket': 'b', **AWS_CREDS},
        }))

        surviving = items_to_legacy_context(wrap_legacy_result(result))
        assert read_envelope(surviving['data'])['rung'] == Outcome.OBSERVED.value

    def test_a_flat_dict_module_lands_its_envelope_in_data_too(self, fake_aioboto3, sandboxed_tmp_path):
        from core.modules.third_party.cloud import storage as module

        fake_aioboto3(FakeAsyncS3(head={'ContentLength': 5}))
        result = _run(module.aws_s3_upload.__wrapped_func__({
            'params': {'bucket': 'b', 'key': 'k', 'content': 'hello'},
        }))

        assert 'data' not in result  # flat: wrap_legacy_result sweeps the fields
        surviving = items_to_legacy_context(wrap_legacy_result(result))
        assert read_envelope(surviving['data'])['rung'] == Outcome.OBSERVED.value

    def test_a_class_module_returning_a_bare_dict_is_still_read(
        self, fake_gcs, sandboxed_tmp_path
    ):
        """The third shape in this group, and the one with no `ok` at all.

        `GCSDownloadModule.execute` returns a bare dict, which the executor
        passes through untouched -- so the envelope sits at the top level and is
        found there. `step_outcome` is the reader that decides what a step is
        allowed to say, so it is the one asked.
        """
        from core.engine.step_executor.executor import step_outcome
        from core.modules.third_party.cloud.gcs import GCSDownloadModule

        fake_gcs(FakeBlob(download_bytes=b'0123456789'))
        result = _run(GCSDownloadModule({
            'bucket': 'b',
            'object_name': 'o',
            'destination_path': str(sandboxed_tmp_path / 'saved.bin'),
        }, {}).execute())

        assert 'ok' not in result
        rung, claim_by, postcondition = step_outcome(result)
        assert rung is Outcome.OBSERVED
        assert claim_by == ClaimBy.NONE.value
        assert postcondition is None
