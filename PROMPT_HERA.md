Create a {{SECONDS}}-second 16:9 motion graphic with a chroma key background.
Background:
Everything outside the banner must be a solid, uniform bright green (#00FF00). No gradients, shadows, noise, compression artifacts, or variation in the green area. This green area will be keyed out in post-production, so it must be perfectly clean and consistent.
Composition:
Full 16:9 frame.
Bottom 25–30% of the frame: a dark, fully opaque horizontal banner spanning the entire width. The banner must be 100% opaque — no transparency, no see-through areas, and no green must bleed through or show behind it.
Top ~70–75% of the frame: entirely solid green background with absolutely no content, text, imagery, or visual elements of any kind.
Banner design:
Dark charcoal to near-black gradient.
Solid, 100% opacity. No transparency layers, no alpha blending with the background.
Clean, modern, editorial lower-third style.
The banner must completely and fully block the green background beneath it at all times.
Text (left-aligned inside the banner):
Title (large, bold): "{{TITLE}}"
Body text (smaller, regular weight): "{{BODY_TEXT}}"
Typography:
Modern sans-serif (Inter / Helvetica / SF Pro style).
White or off-white text.
Clear typographic hierarchy with generous line spacing and padding inside the banner.
Right-side portrait (reference image via API):
A reference image will be provided via an API call. Use this reference to generate and render the portrait natively inside the motion graphic — do not composite an external image file into the scene.
The portrait is displayed inside a perfectly circular frame positioned on the right side of the banner.
The circle slightly overlaps upward into the green area. (The portion overlapping green will be keyed out later; the portion over the banner must remain fully opaque.)
The portrait must be cropped to a perfect circle with clean, anti-aliased edges — no square corners, no jagged pixels.
The generated portrait should be centered and cover-fill the circular frame. If the aspect ratio does not match, crop from the center; do not stretch or distort.
Apply a subtle dark inner shadow or 1px stroke around the circle edge to separate it cleanly from both the banner and the green background.
The circular mask and its rendered contents must be fully opaque where they overlap the banner. No green must show through the portrait or its edges.
Animation:
Duration: exactly "{{SECONDS}}" seconds.
Subtle, refined motion only.
Banner softly fades and slides up into position during the first ~1 second.
Text fades in with slight upward motion.
Portrait gently fades or scales in.
Hold static for the remaining duration.
No flashy effects, no camera shake, no unnecessary motion.
Style:
Minimalist, documentary-style lower third.
Premium explainer or Netflix documentary graphic aesthetic.
Output requirements:
16:9 aspect ratio.
{{SECONDS}} seconds duration.
Solid green (#00FF00) background outside the banner for clean chroma keying.
The banner and all its contents must be fully opaque with zero green contamination.