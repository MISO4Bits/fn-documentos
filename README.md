# fn-documentos

Función serverless (Cloud Run) que **genera el documento de la póliza** (PDF), lo guarda en un
bucket privado y entrega un **enlace temporal** para verlo. Es la función por llamada del
componente "Comunicaciones y Documentos"; `fn-notificaciones` es la de correos.

La función no envía correos y no consulta a nadie: recibe la póliza ya emitida por
CoreTransaccional y la convierte en un documento. Contrato: [`openapi/openapi.yaml`](openapi/openapi.yaml).

## Qué hace

| Entrada | Quién la dispara | Qué pasa |
|---|---|---|
| `POST /` (suscripción push, `tipo = PolizaEmitida`) | Pub/Sub | Genera el PDF, lo guarda en `polizas/{polizaId}.pdf` y publica `DocumentoPolizaGenerado` |
| `POST /v1/documentos/polizas/enlace` | CoreTransaccional | Genera el PDF si falta y devuelve un enlace firmado de unos 15 minutos que abre el PDF en el visor |

Core recibe `DocumentoPolizaGenerado`, arma el correo y lo manda a `fn-notificaciones` con el PDF
como adjunto.

## El documento

Una página A4 con la marca de Solventa (logo y Plus Jakarta Sans, la misma paleta de los correos):
asegurado, coberturas con su prima, vigencia y pago, beneficiario oneroso y la cláusula para el
banco. El número de documento sale enmascarado (`C.C. 1.017.xxx.456`). El mismo dato produce el
mismo PDF. Las fuentes (licencia OFL) están en `app/assets/fonts`.

## Configuración (`FD_*`)

| Variable | Por defecto | Para qué |
|---|---|---|
| `FD_ALMACEN_BACKEND` | `memory` | `memory` (local) o `gcs` (bucket) |
| `FD_ALMACEN_BUCKET` | | Bucket de los PDF (obligatorio con `gcs`) |
| `FD_FIRMANTE_EMAIL` | | Cuenta con la que se firman los enlaces; si falta, la de la función |
| `FD_ENLACE_MINUTOS` | `15` | Vigencia del enlace |
| `FD_PUBLICADOR_BACKEND` | `logging` | `logging` o `pubsub` |
| `FD_PUBSUB_PROJECT_ID` / `FD_PUBSUB_TOPIC` | | Proyecto y tópico (`solventa-dominio`) |

Los enlaces se firman por la API de IAM: la cuenta de servicio necesita
`roles/iam.serviceAccountTokenCreator` sobre sí misma.

## Desarrollo

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest --cov=app
```
