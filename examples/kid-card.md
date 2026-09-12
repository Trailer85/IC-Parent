# Per-student Lovelace markdown

Duplicate this card once per student. Replace `SLUG` with the entity slug
(`alex`, `sam`, …) published by the Infinite Campus poller.

Missing assignment names render red. Score and grade values are green above
89.9, orange above 79.9, and red otherwise, once `school-schedule.js` is loaded.

```yaml
type: markdown
content: |
  {% if is_state('binary_sensor.SLUG_has_missing', 'on') %}**Missing work**

  {% endif %}**Missing** ({{ states('sensor.SLUG_assignments_missing') }})
  {% set items = state_attr('sensor.SLUG_assignments_missing', 'assignments') or [] %}
  {% if items | length == 0 %}_None_{% else %}
  {% for a in items %}
  - <span class="school-missing"><font color="#f87171">{{ a.name }}</font></span> · {{ a.course }}{% if a.due %} · {{ a.due.replace('T', ' ')[:10] }}{% endif %}
  {% endfor %}
  {% endif %}

  **Due today** ({{ states('sensor.SLUG_assignments_due_today') }})
  {% set items = state_attr('sensor.SLUG_assignments_due_today', 'assignments') or [] %}
  {% if items | length == 0 %}_None_{% else %}
  {% for a in items %}
  - {{ a.name }} · {{ a.course }}{% if a.due %} · {{ a.due.replace('T', ' ')[:10] }}{% endif %}
  {% endfor %}
  {% endif %}

  **Due tomorrow** ({{ states('sensor.SLUG_assignments_due_tomorrow') }})
  {% set items = state_attr('sensor.SLUG_assignments_due_tomorrow', 'assignments') or [] %}
  {% if items | length == 0 %}_None_{% else %}
  {% for a in items %}
  - {{ a.name }} · {{ a.course }}{% if a.due %} · {{ a.due.replace('T', ' ')[:10] }}{% endif %}
  {% endfor %}
  {% endif %}

  **Recent scores**
  {% set items = (state_attr('sensor.SLUG_recent_scores', 'assignments') or [])[:8] %}
  {% if items | length == 0 %}_None_{% else %}
  {% for a in items %}
  - {{ a.name }} · {{ a.course }} · {% set earned = a.score if a.score is defined and a.score not in [none, ''] else a.points %}{% set tot = a.total | default(none, true) %}{% set ns = namespace(pct=none, label='') %}{% if earned is defined and earned not in [none, ''] %}{% if tot not in [none, ''] and (tot | float(0)) > 0 %}{% set ns.pct = (earned | float(0)) / (tot | float(1)) * 100 %}{% set ns.label = (earned | string) ~ ' / ' ~ (tot | string) %}{% else %}{% set ns.label = earned %}{% if earned is number %}{% set ns.pct = earned | float(0) %}{% else %}{% set parsed = earned | float(-1) %}{% if parsed != -1 or earned | string in ['-1', '-1.0'] %}{% set ns.pct = parsed %}{% endif %}{% endif %}{% endif %}{% endif %}{% if ns.pct is number and ns.pct > 89.9 %}<span class="school-grade" data-pct="{{ ns.pct }}"><font color="#4ade80">{{ ns.label }}</font></span>{% elif ns.pct is number and ns.pct > 79.9 %}<span class="school-grade" data-pct="{{ ns.pct }}"><font color="#fb923c">{{ ns.label }}</font></span>{% elif ns.pct is number %}<span class="school-grade" data-pct="{{ ns.pct }}"><font color="#f87171">{{ ns.label }}</font></span>{% elif ns.label %}{{ ns.label }}{% endif %}
  {% endfor %}
  {% endif %}

  **Recent grades**
  {% set items = (state_attr('sensor.SLUG_recent_grades', 'grades') or [])[:8] %}
  {% if items | length == 0 %}_None_{% else %}
  {% for g in items %}
  - {{ g.course }}{% if g.task %} · {{ g.task }}{% endif %} · {% set earned = g.score if g.score is defined and g.score not in [none, ''] else g.points %}{% set tot = g.total | default(none, true) %}{% set ns = namespace(pct=none, label='') %}{% if earned is defined and earned not in [none, ''] %}{% if tot not in [none, ''] and (tot | float(0)) > 0 %}{% set ns.pct = (earned | float(0)) / (tot | float(1)) * 100 %}{% set ns.label = (earned | string) ~ ' / ' ~ (tot | string) %}{% else %}{% set ns.label = earned %}{% if earned is number %}{% set ns.pct = earned | float(0) %}{% else %}{% set parsed = earned | float(-1) %}{% if parsed != -1 or earned | string in ['-1', '-1.0'] %}{% set ns.pct = parsed %}{% endif %}{% endif %}{% endif %}{% endif %}{% if ns.pct is number and ns.pct > 89.9 %}<span class="school-grade" data-pct="{{ ns.pct }}"><font color="#4ade80">{{ ns.label }}</font></span>{% elif ns.pct is number and ns.pct > 79.9 %}<span class="school-grade" data-pct="{{ ns.pct }}"><font color="#fb923c">{{ ns.label }}</font></span>{% elif ns.pct is number %}<span class="school-grade" data-pct="{{ ns.pct }}"><font color="#f87171">{{ ns.label }}</font></span>{% elif ns.label %}{{ ns.label }}{% endif %}{% if g.posted %} ({{ g.posted }}){% endif %}
  {% endfor %}
  {% endif %}
```
