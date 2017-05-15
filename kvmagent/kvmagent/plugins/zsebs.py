import os.path
import traceback

from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
import zstacklib.utils.uuidhelper as uuidhelper

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None
        self.totalCapacity = None
        self.availableCapacity = None

class CheckBitsRsp(AgentRsp):
    def __init__(self):
        super(CheckBitsRsp, self).__init__()
        self.existing = False

class GetVolumeSizeRsp(AgentRsp):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

class CreateRootVolumeRsp(AgentRsp):
    def __init__(self):
        super(CreateRootVolumeRsp, self).__init__()
        self.primaryStorageInstallPath = None

class ZStackElasticBlockStoragePlugin(kvmagent.KvmAgent):

    CONNECT_PATH = "/zsebs/connect"
    CREATE_VOLUME_FROM_CACHE_PATH = "/zsebs/createrootvolume"
    DOWNLOAD_BITS_FROM_IMAGESTORE_PATH = "/zsebs/imagestore/download"
    CHECK_BITS_PATH = "/zsebs/bits/check"
    GET_VOLUME_SIZE_PATH = "/zsebs/volume/getsize"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.CONNECT_PATH, self.connect)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_CACHE_PATH, self.create_root_volume)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_IMAGESTORE_PATH, self.download_from_imagestore)
        http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)

        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass

    @staticmethod
    def _get_disk_capacity(mount_point):
        # FIXME use zstack-ebs supplied command line to get disk capacity
        return linux.get_disk_capacity_by_df('/')

    @kvmagent.replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeSizeRsp()
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def connect(self, req):
        raise kvmagent.KvmError('connect not implemented')


    @kvmagent.replyerror
    def create_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateRootVolumeRsp()
        templatePath, volumeUuid = cmd.templatePathInCache, cmd.volumeUuid

        if not os.path.exists(templatePath):
            rsp.error = "UNABLE_TO_FIND_IMAGE_IN_CACHE"
            rsp.success = False
            return jsonobject.dumps(rsp)

        shell.call('drbdcon deploy-volume -name %s -file %s' % (volumeUuid, templatePath))
        output = shell.call('drbdcon show-volume -name ' + volumeUuid)
        volinfo = jsonobject.loads(output)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        rsp.primaryStorageInstallPath = '/dev/drbd'+str(volinfo.minor)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def download_from_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.imagestore_client.download_from_imagestore(cmd.mountPoint, cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath)
        rsp = AgentRsp()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        rsp.existing = os.path.exists(cmd.path)
        return jsonobject.dumps(rsp)
