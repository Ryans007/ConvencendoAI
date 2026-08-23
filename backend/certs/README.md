# Certificado de CA para build atras de proxy

Coloque aqui o arquivo `.crt` da autoridade certificadora corporativa quando o build
precisar rodar numa rede que faz inspecao TLS. Sem isso a instalacao de dependencias
falha com `invalid peer certificate: UnknownIssuer`.

Depois, aponte o nome do arquivo em `CORPORATE_CA_CERT` no `.env`:

    CORPORATE_CA_CERT=minha-ca.crt

Fora dessa rede, deixe a variavel vazia: o build ignora esta pasta por completo.

Nenhum `.crt` deve ser versionado. O `.gitignore` da raiz mantem apenas este README.
