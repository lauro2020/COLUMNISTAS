# Guía breve: añadir un columnista o un medio nuevo

## A. Añadir un columnista (sin tocar código)

Es lo normal. El extractor genérico funciona en casi cualquier periódico.

1. Abre la app → pestaña **Ajustes** → sección **Columnistas**.
2. Pulsa **+ Añadir columnista** y rellena:

   | Campo | Qué poner | Ejemplo |
   |---|---|---|
   | Nombre | El del autor | `Denise Dresser` |
   | Medio | El del periódico. **Debe escribirse igual** que en Credenciales si el medio es de pago | `Reforma` |
   | URL de su página de autor | La página donde el medio lista sus columnas | `https://www.reforma.com/denise-dresser/` |
   | URL del RSS | Déjalo vacío: se descubre solo si el medio lo publica | |
   | Tipo de fuente | `Automático` salvo que sepas que solo hay una vía | `Automático` |
   | Extractor | `Elegir según el dominio`, salvo que quieras forzar uno | |
   | Frecuencia esperada | Solo informativo | `lunes y jueves` |

3. Guarda y pulsa **Probar fuente**. Te dirá:
   - de dónde salieron los artículos (RSS o HTML, y con qué extractor),
   - cuántos encontró y sus títulos,
   - una muestra del texto extraído: cuántos párrafos, cuántas palabras y si
     topó con un muro de pago.

4. Si el resultado es bueno, ya está: entrará en la recolección de mañana. Para
   probarlo ahora, ve a **Fuentes** y pulsa **Recolectar solo esta**.

> Con muchos columnistas, en vez de ir uno por uno:
> `docker compose exec api python -m app.cli check-sources` los prueba todos y
> resume el resultado en una tabla.

### Si la prueba sale mal

| Lo que ves | Qué significa | Qué hacer |
|---|---|---|
| `La fuente falló` + error de red | La URL está mal o el medio no responde | Revisa la URL en el navegador |
| `encontrados: 0` | La página del autor existe pero no se reconocen los enlaces a sus columnas | Prueba con la URL de la sección de opinión, o escribe un extractor (parte B) |
| Muestra con 1-2 párrafos y `muro de pago` | El medio corta el texto para no suscriptores | Guarda tus cookies en **Ajustes → Credenciales** |
| Muestra con texto de menús o anuncios | El extractor genérico eligió mal el bloque | Escribe un extractor (parte B) |
| `HTTP 403 — el medio rechaza a nuestro robot` | El sitio bloquea todo lo que no sea un navegador | Edita el columnista y activa **«Identificarse como navegador»** |
| `redirigió a su pantalla de acceso` | El medio no reconoció tu sesión de suscriptor | Guarda las cookies en **Ajustes → Credenciales** |

---

## B. Añadir un extractor para un medio nuevo

Solo hace falta cuando el genérico no da buen resultado. Es **un solo archivo**;
el sistema lo descubre solo, no hay que registrarlo en ningún sitio.

### 1. Averigua dónde vive el texto

Abre una columna de ese medio en el navegador, pulsa `F12`, y con la herramienta
de selección (la flechita) haz clic sobre un párrafo del artículo. Busca hacia
arriba el contenedor que envuelve **todo** el cuerpo y apunta su `class` o `id`.
Suele llamarse algo como `article-body`, `cuerpo-nota` o `entry-content`.

### 2. Crea el archivo

`backend/app/collector/extractors/mimedio.py`:

```python
from bs4 import BeautifulSoup

from app.collector import dates, normalize
from app.collector.extractors.base import ExtractedArticle
from app.collector.extractors.generic import GenericExtractor


class MiMedioExtractor(GenericExtractor):
    key = "mimedio"                    # identificador único, sin espacios
    domains = ("mimedio.com.mx",)      # dominios que atiende (sin "www.")
    outlet = "Mi Medio"                # nombre legible del medio
    needs_browser = False              # True si el texto solo aparece con JavaScript

    BODY_SELECTORS = ["div.cuerpo-nota", "[itemprop='articleBody']"]

    def extract_from_html(self, html: str, url: str) -> ExtractedArticle | None:
        soup = BeautifulSoup(html, "lxml")
        for selector in self.BODY_SELECTORS:
            node = soup.select_one(selector)
            if not node:
                continue
            blocks = normalize.html_to_blocks(str(node), url)
            if len(blocks) >= 2:
                text = normalize.blocks_to_text(blocks)
                return ExtractedArticle(
                    title=(normalize.extract_title(soup) or "Sin título").strip(),
                    canonical_url=normalize.extract_canonical(soup, url),
                    original_url=url,
                    blocks=blocks,
                    author=self._author(soup),
                    outlet=self.outlet,
                    published_at=dates.extract_published_at(soup, html),
                    summary=normalize.make_summary(text),
                    is_paywalled=normalize.looks_paywalled(
                        text, normalize.count_words(text)),
                    extractor=self.key,
                )
        # Si ningún selector funcionó, que se encargue el genérico
        return super().extract_from_html(html, url)
```

`normalize.html_to_blocks()` ya se encarga de quitar anuncios, banners de
suscripción, "contenido relacionado" y menús, y de conservar enlaces, citas y
subtítulos. Tú solo indicas **dónde** está el cuerpo.

### 3. Si la lista de columnas tampoco se detecta

Añade también un `discover_from_html`, que devuelve los artículos encontrados en
la página del autor:

```python
    def discover_from_html(self, html: str, base_url: str) -> list[ArticleRef]:
        soup = BeautifulSoup(html, "lxml")
        refs = {}
        for anchor in soup.select("article h2 a[href]"):     # ajusta el selector
            url = normalize.canonicalize_url(anchor["href"], base_url)
            refs[url] = ArticleRef(url=url, title=anchor.get_text(" ", strip=True))
        return list(refs.values())[:25] or super().discover_from_html(html, base_url)
```

### 4. Escribe una prueba (recomendado)

Guarda el HTML de una columna real en `backend/tests/fixtures.py` y añade en
`backend/tests/test_extractors.py`:

```python
def test_mimedio_extrae_el_cuerpo():
    article = MiMedioExtractor().extract_from_html(
        fixtures.MIMEDIO_ARTICLE, "https://mimedio.com.mx/columna/")
    assert article is not None
    assert len(article.blocks) >= 3
    assert article.outlet == "Mi Medio"
```

Ejecuta `cd backend && pytest`.

### 5. Aplícalo

```bash
docker compose restart api worker
```

En la ficha del columnista, el campo **Extractor** ya ofrecerá `mimedio`. Puedes
dejarlo en `Elegir según el dominio`: al declarar `domains`, el sistema lo
seleccionará solo para ese medio.

---

## Ejemplos que puedes copiar

| Archivo | Qué resuelve |
|---|---|
| `eluniversal.py` | Caso típico: selectores CSS sobre un Drupal |
| `elfinanciero.py` | El artículo viene en un JSON incrustado (Arc Publishing). Más estable que cualquier selector |
| `reforma.py` | Muro de pago + contenido pintado con JavaScript (`needs_browser = True`) |
| `milenio.py` | Sitio que rechaza al robot: identidad de navegador + `needs_browser` |
| `generic.py` | El respaldo: detección del bloque principal por densidad de texto |
