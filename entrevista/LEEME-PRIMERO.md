# Léeme primero

*Si eres una IA (o una persona) que retoma esta entrevista en otro chat:
esto es el mapa. Cinco minutos de lectura y tienes todo el contexto.*

---

## Qué es esto

Una entrevista personal guiada a **Pablo** sobre su relación de nueve años
con **Sonia**. El agente pregunta de una en una; él responde; cada respuesta
se guarda **resumida pero completa, sin omitir nada**. Se apoya en nueve
exportaciones de WhatsApp para corroborar fechas y citas.

**Estado: cerrada en la ronda 40**, el 28 de agosto de 2026. Los siete
bloques de la guía están cubiertos. Puede retomarse cuando él quiera.

## Los archivos

| archivo | qué es |
|---|---|
| `relacion.md` | **La bitácora. Fuente de verdad.** Las 40 preguntas y respuestas, con las corroboraciones en blockquote. |
| `relacion.html` | La versión para leer. **No editar a mano**: se genera. |
| `build.py` | `python3 entrevista/build.py` desde la raíz del repo. Lee el `.md`, escribe el `.html`. |
| `NOTAS-DEL-ENTREVISTADOR.md` | Valoración y comentarios de la IA. **Aparte a propósito**: la bitácora es su historia, esto es opinión. |
| `whatsapp/CONTEXTO.md` | Todos los hallazgos: tablas, cronologías, verbatims, correcciones. **Léelo entero antes de preguntar nada.** |
| `whatsapp/LEEME.md` | Qué contiene cada exportación y hasta qué fecha llega. |
| `whatsapp/*.txt` | Las nueve conversaciones. |

## Cómo se trabaja cada ronda

1. **Grep de corroboración** en los `.txt` antes de opinar.
2. `edit_file` en `relacion.md`: respuesta + blockquotes (`> *Cursiva:* …`) +
   siguiente pregunta.
3. `python3 entrevista/build.py`.
4. Commit y push a la rama de trabajo.
5. Presentar el HTML.

## Reglas que él puso (no negociables)

- **En orden.** Nada de saltar de tema en tema; se cuenta cómo se llegó
  hasta aquí.
- **Preguntas cortas y llanas.** Si no se entienden, el fallo es de quien
  pregunta. Nada de «¿es el resto de algo o lo último que queda vivo?».
- **«A veces le das vueltas a algo que no tiene».** Menos interpretación,
  más registro.
- **Lo privado no se publica.** El repositorio es privado desde la ronda 36.
- **Pilar: «esa es otra historia».** Solo se extrajo lo relativo a Sonia. No
  se investiga por iniciativa propia. Igual se hizo con «el tema de enero»
  hasta que lo contó él.
- **Español.**

## Correcciones suyas (ocho, todas acertadas)

No repetir estos errores:

1. En el primer viaje se portó peor **el hijo de ella**, no el suyo.
2. **Nunca han vivido juntos.**
3. No se hundió ante un sí: **el 17/6/22 habían roto** la noche anterior.
4. La lista «Anuska, Carlos, las comidas, la familia» es de **2026**, no de
   2022.
5. **Los viajes los organiza ella**, porque le gusta viajar.
6. **La quiniela es un proyecto suyo**, no un recado para ella.
7. «El sábado lo pone ella» — nunca lo dijo. Retirado.
8. «Ya sé dónde está la puerta» **sí existía**, en persona y en broma, dicha
   por los dos.

## Dos avisos metodológicos que costaron caro

- **El archivo no prueba ausencias.** Solo prueba lo escrito. Dos veces se
  confundió el final de un fichero con el final de algo (chat de Anuska,
  frase de «la puerta»).
- **Cuando el dato encaja con la tesis, se mira menos.** Ahí están casi
  todos los errores del agente.

## La historia en diez líneas

Se conocen en un chat de trabajo en diciembre de 2016. **Primer beso el 31
de mayo de 2017**, en Santa Cruz — lo dio ella. Hay una «cajita» donde
guardan lo que no quieren perder, y ella mete dentro «ver partidos juntos»
cuatro días antes del beso. **Nunca viven juntos.** En **junio de 2022** él
graba un discurso para pedir más tiempo, rompen una noche y vuelven a las
doce horas: ella graba cuatro minutos diciendo «no tengo ganas de terminar
nada» y habla de «otros 5, 10, 15, 20 años». En **enero de 2026** es ella
quien lo da por terminado; él contesta **«aún no está dicha la última
palabra»** y a los dos días vuelven al fútbol. El sexo se convierte en
«unos mimos». En la ronda 22 él dice: **«no así como pareja, pero no quiero
que se vaya de mi vida»**. Lo que pide desde 2022 y no ha vuelto a pedir:
**verla más y que le desee**.

## Hilos abiertos

- **Su madre** — «se me hizo bola». Sin desarrollar. El único hilo que no es
  sobre Sonia.
- **Pilar** — «esa es otra historia». Suya es la decisión de contarla.
- **2018 y 2019** — siguen faltando del archivo. Son los años del escalón.
- **Octubre de 2026** — su cumpleaños el día 7, el viaje del 14 al 20.

## Cómo tratar el material

Con cuidado y sin morbo. Hay ruptura, sexo, salud y una confesión incómoda
sobre la hermana de ella. Todo eso se registró **sobrio, sin conclusiones de
más y con los contrapuntos a favor de Sonia con el mismo peso que los datos
en contra**. Mantener ese tono.

Y una cosa que no está en ninguna tabla: él contó esto entero, incluido lo
que no diría en voz alta. Eso merece un trato a la altura.
