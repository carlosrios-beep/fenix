"""Servidor local ligero que emula APIs de AWS (SQS, EC2 mock y S3) en el puerto 4566."""

import http.server
import json
import socketserver
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

PORT = 4566

QUEUES = {
    "fenix-events-queue": [],
    "fenix-events-dlq": [],
}
RECEIPT_HANDLES = {}
INSTANCES = {}
BUCKETS = {}


class MockAWSHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if "_localstack/health" in parsed.path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"services": {"sqs": "running", "ec2": "running", "s3": "running"}}).encode("utf-8"))
            return

        if "tagging" in parsed.query:
            bucket_name = parsed.path.strip("/")
            tags = BUCKETS.get(bucket_name, {}).get("tags", {})
            tag_set_xml = "".join(f"<Tag><Key>{k}</Key><Value>{v}</Value></Tag>" for k, v in tags.items())
            xml = f"""<Tagging xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
                <TagSet>{tag_set_xml}</TagSet>
            </Tagging>"""
            self._send_xml(xml)
            return

        self.send_response(200)
        self.end_headers()

    def do_PUT(self):
        parsed = urlparse(self.path)
        bucket_name = parsed.path.strip("/").split("/")[0]

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b""

        if "tagging" in parsed.query:
            try:
                root = ET.fromstring(body)
                tags = {}
                for tag in root.findall(".//Tag"):
                    k = tag.find("Key").text
                    v = tag.find("Value").text
                    tags[k] = v
                if bucket_name not in BUCKETS:
                    BUCKETS[bucket_name] = {}
                BUCKETS[bucket_name]["tags"] = tags
            except Exception:
                pass
            self.send_response(200)
            self.end_headers()
            return

        if bucket_name not in BUCKETS:
            BUCKETS[bucket_name] = {"tags": {}}
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else ""
        content_type = self.headers.get("Content-Type", "")

        is_json = "json" in content_type or raw_body.strip().startswith("{")
        target_header = self.headers.get("X-Amz-Target", "")

        if is_json and raw_body:
            try:
                json_data = json.loads(raw_body)
            except Exception:
                json_data = {}
            action = target_header.split(".")[-1] if target_header else ""
            params = {k: [str(v)] for k, v in json_data.items()}
        else:
            params = parse_qs(raw_body)
            action = params.get("Action", [None])[0]

        # 1. Rutas SQS
        if action == "CreateQueue":
            q_name = params.get("QueueName", ["fenix-events-queue"])[0]
            if q_name not in QUEUES:
                QUEUES[q_name] = []
            q_url = f"http://127.0.0.1:4566/000000000000/{q_name}"
            if is_json:
                self._send_json({"QueueUrl": q_url})
            else:
                xml = f"""<CreateQueueResponse xmlns="http://queue.amazonaws.com/doc/2012-11-05/">
                    <CreateQueueResult><QueueUrl>{q_url}</QueueUrl></CreateQueueResult>
                    <ResponseMetadata><RequestId>mock-req</RequestId></ResponseMetadata>
                </CreateQueueResponse>"""
                self._send_xml(xml)

        elif action == "GetQueueAttributes":
            attrs = {"QueueArn": "arn:aws:sqs:us-east-1:000000000000:fenix-dlq"}
            if is_json:
                self._send_json({"Attributes": attrs})
            else:
                xml = f"""<GetQueueAttributesResponse xmlns="http://queue.amazonaws.com/doc/2012-11-05/">
                    <GetQueueAttributesResult>
                        <Attribute><Name>QueueArn</Name><Value>{attrs['QueueArn']}</Value></Attribute>
                    </GetQueueAttributesResult>
                    <ResponseMetadata><RequestId>mock-req</RequestId></ResponseMetadata>
                </GetQueueAttributesResponse>"""
                self._send_xml(xml)

        elif action == "SendMessage":
            q_name = self._extract_queue_name(params)
            msg_body = params.get("MessageBody", ["{}"])[0]
            msg_id = str(uuid.uuid4())
            QUEUES.setdefault(q_name, []).append({
                "id": msg_id,
                "body": msg_body,
                "receive_count": 0,
            })
            if is_json:
                self._send_json({"MessageId": msg_id, "MD5OfMessageBody": "mock"})
            else:
                xml = f"""<SendMessageResponse xmlns="http://queue.amazonaws.com/doc/2012-11-05/">
                    <SendMessageResult><MessageId>{msg_id}</MessageId><MD5OfMessageBody>mock</MD5OfMessageBody></SendMessageResult>
                    <ResponseMetadata><RequestId>mock-req</RequestId></ResponseMetadata>
                </SendMessageResponse>"""
                self._send_xml(xml)

        elif action == "ReceiveMessage":
            q_name = self._extract_queue_name(params)
            msgs = QUEUES.get(q_name, [])
            if msgs:
                m = msgs[0]
                m["receive_count"] += 1
                rh = str(uuid.uuid4())
                RECEIPT_HANDLES[rh] = (q_name, m)
                if is_json:
                    self._send_json({
                        "Messages": [{
                            "MessageId": m['id'],
                            "ReceiptHandle": rh,
                            "MD5OfBody": "mock",
                            "Body": m['body'],
                            "Attributes": {"ApproximateReceiveCount": str(m['receive_count'])}
                        }]
                    })
                else:
                    xml = f"""<ReceiveMessageResponse xmlns="http://queue.amazonaws.com/doc/2012-11-05/">
                        <ReceiveMessageResult>
                            <Message>
                                <MessageId>{m['id']}</MessageId>
                                <ReceiptHandle>{rh}</ReceiptHandle>
                                <MD5OfBody>mock</MD5OfBody>
                                <Body>{m['body']}</Body>
                                <Attribute><Name>ApproximateReceiveCount</Name><Value>{m['receive_count']}</Value></Attribute>
                            </Message>
                        </ReceiveMessageResult>
                        <ResponseMetadata><RequestId>mock-req</RequestId></ResponseMetadata>
                    </ReceiveMessageResponse>"""
                    self._send_xml(xml)
            else:
                if is_json:
                    self._send_json({"Messages": []})
                else:
                    xml = """<ReceiveMessageResponse xmlns="http://queue.amazonaws.com/doc/2012-11-05/">
                        <ReceiveMessageResult></ReceiveMessageResult>
                        <ResponseMetadata><RequestId>mock-req</RequestId></ResponseMetadata>
                    </ReceiveMessageResponse>"""
                    self._send_xml(xml)

        elif action == "DeleteMessage":
            rh = params.get("ReceiptHandle", [""])[0]
            if rh in RECEIPT_HANDLES:
                q_name, m = RECEIPT_HANDLES.pop(rh)
                if m in QUEUES.get(q_name, []):
                    QUEUES[q_name].remove(m)
            if is_json:
                self._send_json({})
            else:
                xml = """<DeleteMessageResponse xmlns="http://queue.amazonaws.com/doc/2012-11-05/">
                    <ResponseMetadata><RequestId>del-ok</RequestId></ResponseMetadata>
                </DeleteMessageResponse>"""
                self._send_xml(xml)

        elif action == "ChangeMessageVisibility":
            if is_json:
                self._send_json({})
            else:
                xml = """<ChangeMessageVisibilityResponse xmlns="http://queue.amazonaws.com/doc/2012-11-05/">
                    <ResponseMetadata><RequestId>vis-ok</RequestId></ResponseMetadata>
                </ChangeMessageVisibilityResponse>"""
                self._send_xml(xml)

        # 2. Rutas EC2 mock
        elif action == "DescribeVpcs":
            xml = """<DescribeVpcsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <vpcSet><item><vpcId>vpc-mock01</vpcId></item></vpcSet>
            </DescribeVpcsResponse>"""
            self._send_xml(xml)

        elif action == "DescribeImages":
            xml = """<DescribeImagesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <imagesSet><item><imageId>ami-mock01</imageId></item></imagesSet>
            </DescribeImagesResponse>"""
            self._send_xml(xml)

        elif action == "CreateSecurityGroup":
            xml = """<CreateSecurityGroupResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <groupId>sg-mock01</groupId>
            </CreateSecurityGroupResponse>"""
            self._send_xml(xml)

        elif action == "RunInstances":
            inst_id = f"i-{uuid.uuid4().hex[:8]}"
            INSTANCES[inst_id] = {"state": "running"}
            xml = f"""<RunInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <instancesSet><item><instanceId>{inst_id}</instanceId><instanceState><name>running</name></instanceState></item></instancesSet>
            </RunInstancesResponse>"""
            self._send_xml(xml)

        elif action == "StopInstances":
            inst_id = params.get("InstanceId.1", ["i-mock"])[0]
            if inst_id in INSTANCES:
                INSTANCES[inst_id]["state"] = "stopped"
            xml = f"""<StopInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <instancesSet><item><instanceId>{inst_id}</instanceId><currentState><name>stopped</name></currentState></item></instancesSet>
            </StopInstancesResponse>"""
            self._send_xml(xml)

        elif action == "StartInstances":
            inst_id = params.get("InstanceId.1", ["i-mock"])[0]
            if inst_id in INSTANCES:
                INSTANCES[inst_id]["state"] = "running"
            xml = f"""<StartInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <instancesSet><item><instanceId>{inst_id}</instanceId><currentState><name>running</name></currentState></item></instancesSet>
            </StartInstancesResponse>"""
            self._send_xml(xml)

        elif action == "DescribeInstances":
            items = "".join(
                f"<item><instanceId>{i}</instanceId><instanceState><name>{data['state']}</name></instanceState></item>"
                for i, data in INSTANCES.items()
            )
            xml = f"""<DescribeInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <reservationSet><item><instancesSet>{items}</instancesSet></item></reservationSet>
            </DescribeInstancesResponse>"""
            self._send_xml(xml)

        else:
            self.send_response(200)
            self.end_headers()

    def _extract_queue_name(self, params) -> str:
        q_url = params.get("QueueUrl", [""])[0]
        if q_url:
            return q_url.strip("/").split("/")[-1]
        parts = self.path.strip("/").split("/")
        return parts[-1] if parts else "fenix-events-queue"

    def _send_xml(self, xml_str: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/xml")
        self.end_headers()
        self.wfile.write(xml_str.encode("utf-8"))

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-amz-json-1.0")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", PORT), MockAWSHandler) as httpd:
        print(f"Emulador AWS Mock corriendo en http://127.0.0.1:{PORT} (SQS, EC2, S3 sin Docker)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDeteniendo emulador...")
