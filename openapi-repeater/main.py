from java.io import BufferedReader, FileReader, File
from burp import IBurpExtender, ITab
from javax.swing import JPanel, JButton, JTextField, JFileChooser, JLabel, SwingUtilities, BoxLayout
from java.awt import FlowLayout, GridBagConstraints, GridBagLayout
import json
import java.net.URL as JURL

class BurpExtender(IBurpExtender, ITab):

    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        self._callbacks.setExtensionName("OpenAPI to Repeater")

        self.wrapperPanel = JPanel(GridBagLayout())
        self._panel = JPanel()
        self._panel.setLayout(BoxLayout(self._panel, BoxLayout.Y_AXIS))

        self._hostPanel = JPanel(FlowLayout(FlowLayout.CENTER))
        self._hostLabel = JLabel("Enter API Host:")
        self._hostField = JTextField(30)
        self._hostPanel.add(self._hostLabel)
        self._hostPanel.add(self._hostField)

        self._CookiePanel = JPanel(FlowLayout(FlowLayout.CENTER))
        self._CookieLabel = JLabel("Add Cookies:")
        self._CookieField = JTextField(30)
        self._CookiePanel.add(self._CookieLabel)
        self._CookiePanel.add(self._CookieField)

        self._filePanel = JPanel(FlowLayout(FlowLayout.CENTER))
        self._label = JLabel("Upload Swagger/OpenAPI JSON:")
        self._uploadButton = JButton("Choose File", actionPerformed=self.fileChooser)
        self._filePanel.add(self._label)
        self._filePanel.add(self._uploadButton)

        self._loadPanel = JPanel(FlowLayout(FlowLayout.CENTER))
        self._loadButton = JButton("Load to Repeater", actionPerformed=self.loadSwaggerToRepeater)
        self._loadPanel.add(self._loadButton)

        self._panel.add(self._hostPanel)
        self._panel.add(self._CookiePanel)
        self._panel.add(self._filePanel)
        self._panel.add(self._loadPanel)

        gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.weightx = 1
        gbc.weighty = 1
        gbc.anchor = GridBagConstraints.CENTER
        self.wrapperPanel.add(self._panel, gbc)

        SwingUtilities.invokeLater(lambda: callbacks.addSuiteTab(self))

    def getTabCaption(self):
        return "OpenAPI to Repeater"

    def getUiComponent(self):
        return self.wrapperPanel

    def fileChooser(self, event):
        chooser = JFileChooser()
        returnValue = chooser.showOpenDialog(self._panel)
        
        if returnValue == JFileChooser.APPROVE_OPTION:
            self.selectedFile = chooser.getSelectedFile()

    def loadSwaggerToRepeater(self, event):
        if not hasattr(self, 'selectedFile'):
            self._callbacks.issueAlert("Please choose a Swagger/OpenAPI JSON file!")
            return

        file = self.selectedFile
        reader = BufferedReader(FileReader(file))

        cookie = self._CookieField.getText()
        host = self._hostField.getText()
        if not host:
            self._callbacks.issueAlert("Please provide a valid API Host!")
            return

        try:
            content = []
            line = reader.readLine()
            while line is not None:
                content.append(line)
                line = reader.readLine()
            content_str = ''.join(content)

            swagger_spec = json.loads(content_str)

            for pathKey, methods in swagger_spec["paths"].items():
                for methodName, details in methods.items():
                    query_params = []
                    if 'parameters' in details:
                        for param in details['parameters']:
                            if param['in'] == 'query':
                                default_val = param.get('default', '')
                                query_params.append('{}={}'.format(param['name'], default_val))

                    request_url = "{}{}".format(host, pathKey)
                    if query_params:
                        request_url = "{}?{}".format(request_url, '&'.join(query_params))

                    url = JURL(request_url)

                    if url.getPort() == -1:
                        if url.getProtocol() == "https":
                            port = 443
                        else:
                            port = 80
                    else:
                        port = url.getPort()

                    http_service = self._helpers.buildHttpService(url.getHost(), port, url.getProtocol() == "https")

                    headers = [
                        "{} {} HTTP/1.1".format(methodName.upper(), pathKey + ('?' + '&'.join(query_params) if query_params else '')),  # This ensures query params are in the request line
                        "Host: %s" % url.getHost()
                    ]
                    
                    if len(cookie) > 0:
                        headers.append("Cookie: %s" % cookie)

                    if 'parameters' in details:
                        default_headers = {param['name']: param.get('default', '') for param in details['parameters'] if param['in'] == 'header'}
                        for header, value in default_headers.items():
                            headers.append("{}: {}".format(header, value))

                    if 'requestBody' in details and methodName.upper() == "POST":
                        if "Content-Type" not in [h.split(":")[0].strip() for h in headers]:
                            headers.append("Content-Type: application/json")

                        ref = details['requestBody']['content']['application/json']['schema']['$ref']
                        body_schema = swagger_spec['components']['schemas'][ref.split('/')[-1]]
                        body = {}
                        if 'properties' in body_schema:
                            for key, val in body_schema['properties'].items():
                                default_val = val.get('default', '')
                                body[key] = default_val

                        body_str = json.dumps(body)
                        request = self._helpers.buildHttpMessage(headers, body_str)

                    else:
                        request = self._helpers.buildHttpRequest(url)
                        request = self._helpers.buildHttpMessage(headers, "")

                    self._callbacks.sendToRepeater(http_service.getHost(), http_service.getPort(), http_service.getProtocol() == "https", request, methodName.upper() + " " + pathKey)

        except Exception as e:
            self._callbacks.printError("Error: %s" % str(e))
        finally:
            reader.close()
