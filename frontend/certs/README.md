# Certificado de CA para build atras de proxy

Mesmo mecanismo do backend, para o `npm ci` da imagem do frontend. Coloque aqui o `.crt`
da autoridade certificadora corporativa quando o build rodar numa rede que faz inspecao
TLS, e aponte o nome do arquivo em `CORPORATE_CA_CERT` no `.env`.

Fora dessa rede, deixe a variavel vazia: o build ignora esta pasta.

Nenhum `.crt` deve ser versionado.
