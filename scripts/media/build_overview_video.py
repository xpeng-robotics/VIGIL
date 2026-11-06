#!/usr/bin/env python3
"""Render VIGIL's task families, dataset coverage and evaluation definitions.

Uses manuscript RGB examples, selected archived actions and actual house geometry.
Optional authoring dependencies: Pillow, numpy, imageio-ffmpeg. No model or simulator.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import textwrap
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
W, H, FPS, DURATION = 1920, 1080, 24, 152
PAPER = (242, 239, 231)
INK = (8, 20, 29)
TEAL = (88, 220, 190)
MUTED = (139, 160, 165)
WHITE = (250, 249, 244)
CLAY = (245, 149, 111)
PANEL = (19, 38, 47)
LINE = (49, 72, 78)
STARTS = (0, 5, 12, 19, 26, 33, 40, 47, 54, 61, 73, 87, 105, 114, 124, 136, 145)
LABELS = ('INTRODUCING VIGIL', 'PIXEL GROUNDING', 'DISTANCE APPROACH',
          'VIEW SEARCH', 'STATE VERIFICATION', 'APPROACH AND INTERACT',
          'SEARCH AND INTERACT', 'SEQUENTIAL MANIPULATION', 'CONSTRAINT RESOLVING',
          'DEMO 01 / OPEN AND REPORT', 'DEMO 02 / PICK AND PLACE',
          'DEMO 03 / AFTER ATTAINMENT',
          'THE DATASET', 'SCENE COVERAGE', 'WHAT WE MEASURE', 'WHY EPISODES FAIL',
          'WORLD STATE AND TERMINAL COMMITMENT')
DEMOS = (
    dict(case='verified-fridge', start=61, duration=12, reset=1,
         action_seconds=[1.3, 1.3, 1.3, 2.6, 1.5], title='Open the fridge. Then report success.'),
    dict(case='sequential-apple', start=73, duration=14, reset=1,
         action_seconds=[1.1, 1.1, 2.6, 1.5, 3.0, 1.5], title='Pick up the apple. Place it in the sink.'),
    dict(case='post-goal-kettle', start=87, duration=18, reset=.8,
         action_seconds=[.35]*8 + [4] + [.4]*16, title='Open the kettle. Then report success.'),
)
FAMILIES = [
    dict(code='PG', name='Pixel grounding', budget=5, images=['task-pg-chair.jpg'],
         task='Select the chair in the image.',
         condition='The target is already visible\nand within reach.',
         goal='Ground the correct object pixel,\nthen report completion.',
         stages=['Locate', 'Click', 'Report']),
    dict(code='DA', name='Distance approach', budget=12, images=['task-da-far.jpg', 'task-da-near.jpg'],
         task='Move close to the lamp.',
         condition='Seeing an object is only\nthe starting point.',
         goal='Navigate into interaction range\n(about 1.5 m), then report.',
         stages=['See', 'Approach', 'Report']),
    dict(code='VS', name='View search', budget=20, images=['task-vs-hidden.jpg', 'task-vs-visible.jpg'],
         task='Find the garbage can.',
         condition='The target starts outside\nthe current view.',
         goal='Explore until the target is visible,\nthen report that it was found.',
         stages=['Explore', 'Find', 'Report']),
    dict(code='SV', name='State verification', budget=5, case='verified-microwave',
         task='Is the microwave open or closed?',
         condition='Inspect the visible state.\nNo physical interaction is needed.',
         goal='Report the observed category:\nopen / closed or on / off.',
         stages=['Observe', 'Judge', 'Report']),
    dict(code='AI', name='Approach and interact', budget=25, case='verified-fridge',
         task='Open the fridge.',
         condition='The target starts visible.\nApproach it as needed.',
         goal='Perform the requested interaction,\nthen report the resulting state.',
         stages=['Approach', 'Interact', 'Report']),
    dict(code='SI', name='Search and interact', budget=35, images=['task-si-search.jpg', 'task-si-open.jpg'],
         task='Find the fridge, then open it.',
         condition='The target starts out of view.\nFinding it is only one stage.',
         goal='Search, approach and interact,\nthen report completion.',
         stages=['Search', 'Approach', 'Interact', 'Report']),
    dict(code='SM', name='Sequential manipulation', budget=30, case='sequential-apple',
         task='Pick up the apple. Put it in the sink.',
         condition='Several interactions must\nhappen in the right order.',
         goal='Complete an ordered manipulation\nchain, such as pick and place.',
         stages=['Pick', 'Carry', 'Place', 'Report']),
    dict(code='CR', name='Constraint resolving', budget=40, images=['task-cr-route.jpg', 'task-cr-interact.jpg'],
         task='Reach the stove and turn it on.',
         condition='A constraint blocks\nthe direct approach.',
         goal='Resolve the blocked approach,\nthen interact and report.',
         stages=['Plan', 'Resolve', 'Interact', 'Report']),
]
SUBTITLES = [
    (0, 5, 'VIGIL tests what embodied agents can do, and whether they report correctly.'),
    (5, 8.5, 'PG: select the correct pixel on a visible, reachable object.'),
    (8.5, 12, 'This isolates visual grounding, followed by an explicit completion report.'),
    (12, 15.5, 'DA: the target is visible, but the agent must move closer.'),
    (15.5, 19, 'Reach interaction range, then report. No object manipulation is required.'),
    (19, 22.5, 'VS: the target is initially outside the current view.'),
    (22.5, 26, 'Search by changing viewpoint, find the target, and report.'),
    (26, 29.5, 'SV: inspect an object without changing it.'),
    (29.5, 33, 'Report its actual state: open or closed, on or off.'),
    (33, 36.5, 'AI: approach a visible target and perform the requested interaction.'),
    (36.5, 40, 'Here, the agent opens the fridge and then reports completion.'),
    (40, 43.5, 'SI: first find a target that starts out of view.'),
    (43.5, 47, 'Then approach, interact, and report. Search alone does not finish the task.'),
    (47, 50.5, 'SM: complete an ordered sequence, such as picking up and placing an object.'),
    (50.5, 54, 'This archived apple example uses the labeled action-feedback intervention.'),
    (54, 57.5, 'CR: a physical constraint blocks the direct approach.'),
    (57.5, 61, 'Resolve it or find a clear route, then complete the interaction and report.'),
    (61, 65.9, 'Demo 1: turn toward the fridge and approach. A blocked move is retained.'),
    (65.9, 68.5, 'The recorded pixel interaction opens the fridge.'),
    (68.5, 73, 'The agent reports success. The final world state supports that report.'),
    (73, 76.2, 'Demo 2: approach the apple and look down.'),
    (76.2, 80.3, 'Pick up the apple, then turn toward the sink.'),
    (80.3, 83.3, 'Place the held apple into the sink at the executed image pixel.'),
    (83.3, 87, 'The matching report completes the chain. This case uses action feedback.'),
    (87, 90.6, 'Demo 3: approach the kettle. All blocked attempts remain in the replay.'),
    (90.6, 94.6, 'Action nine opens the lid. Compare the original before-and-after observations.'),
    (94.6, 101, 'The goal stays met, but sixteen more actions follow without a report.'),
    (101, 105, 'Budget exhausted: world complete, benchmark unsuccessful. Action-feedback case.'),
    (105, 109.5, 'The frozen benchmark contains 1,000 episodes: 125 in each of eight families.'),
    (109.5, 114, 'It includes 265 iTHOR episodes and 735 ProcTHOR episodes.'),
    (114, 119, 'Coverage spans 69 iTHOR scene names and 465 included ProcTHOR houses.'),
    (119, 124, 'The house assets include kitchens, living rooms, bedrooms and bathrooms.'),
    (124, 130, 'W checks the final world goal. B also requires a matching terminal report.'),
    (130, 136, 'The gap W minus B measures achieved goals not converted into correct closure.'),
    (136, 139, 'FR: the report contradicts the final world state or expected state label.'),
    (139, 142, 'NR: the step budget expires without a report.'),
    (142, 145, 'IL: the invalid-action limit forces termination. Read these measures together.'),
    (145, 152, 'VIGIL separates world completion from correct terminal commitment.'),
]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def mix(a, b, u):
    return tuple(round(x + (y - x) * u) for x, y in zip(a, b))


@lru_cache(maxsize=160)
def font(size, style='sans'):
    paths = {
        'sans': [('/System/Library/Fonts/HelveticaNeue.ttc', 0),
                 ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 0)],
        'bold': [('/System/Library/Fonts/Avenir Next.ttc', 0),
                 ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 0)],
        'serif': [('/System/Library/Fonts/Supplemental/Georgia.ttf', 0),
                  ('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf', 0)],
        'mono': [('/System/Library/Fonts/Menlo.ttc', 0),
                 ('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 0)],
    }
    for path, index in paths[style]:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=index)
    raise SystemExit('Install DejaVu fonts, or use the system fonts on macOS.')


def text(draw, xy, value, size=30, color=INK, style='sans', spacing=10):
    draw.multiline_text(xy, value, font=font(size, style), fill=color, spacing=spacing)


def spaced(draw, xy, value, color=MUTED, size=21, tracking=4):
    x, y = xy
    for ch in value:
        draw.text((x, y), ch, font=font(size, 'mono'), fill=color)
        x += draw.textlength(ch, font=font(size, 'mono')) + tracking


class Film:
    def __init__(self, assets):
        self.assets = assets
        self.manifest = json.loads((assets / 'manifest.json').read_text())
        for item in self.manifest['assets']:
            if hashlib.sha256((assets / item['file']).read_bytes()).hexdigest() != item['asset_sha256']:
                raise ValueError('Changed media source: ' + item['file'])
        self.facts = json.loads((assets / 'benchmark-facts.json').read_text())
        hashes = {self.facts['pack_file']: self.facts['pack_sha256'], **self.facts['house_files'],
                  **self.manifest['replay_files']}
        for name, expected in hashes.items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError('Changed evidence: ' + name)
        self.images = {p.name: Image.open(p).convert('RGB') for p in assets.glob('task-*.jpg')}
        self.cases, self.case_images = {}, {}
        for case in json.loads((ROOT / 'examples/recorded-runs/catalog.json').read_text())['cases']:
            folder = ROOT / 'examples/recorded-runs' / case['id']
            case['trace'] = json.loads((folder / 'traces' / (case['episode_id'] + '.json')).read_text())
            provenance = json.loads((folder / 'provenance.json').read_text())
            self.case_images[case['id']] = [Image.open(folder / f['file']).convert('RGB') for f in provenance['frames']]
            self.cases[case['id']] = case
        for demo in DEMOS:
            if len(demo['action_seconds']) != len(self.cases[demo['case']]['trace']['steps']):
                raise ValueError('Demo timing must retain every recorded action')
            if demo['reset'] + sum(demo['action_seconds']) >= demo['duration']:
                raise ValueError('Demo requires a final outcome hold')
        self.layouts = [json.loads((ROOT / name).read_text()) for name in self.facts['layout_examples']]
        self.room_colors = {'Kitchen': TEAL, 'LivingRoom': (130, 163, 222),
                            'Bedroom': (194, 154, 210), 'Bathroom': CLAY}

    def base(self, chapter):
        im = Image.new('RGB', (W, H), INK); d = ImageDraw.Draw(im)
        text(d, (80, 46), 'VIGIL', 28, WHITE, 'bold')
        d.line((205, 50, 205, 79), fill=TEAL, width=2)
        spaced(d, (228, 53), LABELS[chapter], MUTED, 18, 2)
        text(d, (1740, 48), f'{chapter+1:02d} / {len(STARTS):02d}', 20, MUTED, 'mono')
        d.line((80, 108, 1840, 108), fill=LINE, width=1)
        return im, d

    def family_strip(self, d, active, t):
        for j, family in enumerate(FAMILIES):
            x = 80 + j * 222
            col = TEAL if j < 4 else CLAY
            d.rounded_rectangle((x, 925, x + 204, 984), 8, fill=PANEL,
                                outline=col if j == active else LINE, width=2)
            text(d, (x + 19, 936), family['code'], 27, col if j <= active else MUTED, 'mono')
            text(d, (x + 98, 944), '125', 20, MUTED, 'mono')
            if j == active:
                d.line((x + 3, 984, x + 3 + 198 * min(t / 7, 1), 984), fill=col, width=3)

    def title(self, t):
        im, d = self.base(0)
        spaced(d, (86, 180), 'AN EMBODIED BENCHMARK', TEAL, 21, 3)
        text(d, (70, 247), 'VIGIL', 190, WHITE, 'bold')
        text(d, (83, 491), 'Done, But Not Sure.', 78, WHITE, 'serif')
        text(d, (88, 630), 'What can an agent do?\nWhen should it report?', 43, MUTED, spacing=18)
        d.line((1120, 200, 1120, 900), fill=LINE, width=1)
        im.paste(self.case_images['verified-fridge'][0], (1200, 300)); d = ImageDraw.Draw(im)
        spaced(d, (1200, 246), 'FIRST-PERSON RGB', TEAL, 20, 2)
        text(d, (1200, 826), 'Task + RGB + bounded dialogue history', 25, WHITE)
        text(d, (1200, 880), 'No privileged state in the model input', 24, MUTED)
        text(d, (88, 894), 'Eight task families. One reporting contract.', 31, TEAL)
        return im

    def family(self, index, t):
        chapter = index + 1; f = FAMILIES[index]; col = TEAL if index < 4 else CLAY
        im, d = self.base(chapter)
        text(d, (76, 137), f['code'], 106, col, 'serif')
        text(d, (295, 169), f['name'], 61, WHITE, 'serif')
        tier = 'DIAGNOSTIC' if index < 4 else 'COMPOSITIONAL'
        spaced(d, (300, 256), f"{tier} / {f['budget']}-STEP BUDGET / 125 EPISODES", MUTED, 18, 1)
        label = 'PAPER EXAMPLE / ILLUSTRATIVE VIEWS'
        if 'images' in f:
            images = f['images']; state = min(len(images)-1, int(t >= 3.3))
            picture = self.images[images[state]]
            if len(images) == 2:
                label = 'PAPER EXAMPLE / ' + ('START VIEW' if state == 0 else 'TARGET VIEW')
            note = 'Original embedded RGB from the manuscript figure'
        else:
            cid = f['case']; case = self.cases[cid]; steps = case['trace']['steps']
            position = max(0, t - .3) / 5.8 * len(steps)
            step = min(len(steps)-1, int(position)); phase = position-step
            observation = min(len(steps), step + int(phase >= .52 or position >= len(steps)))
            picture = self.case_images[cid][observation]
            action = steps[step]['metadata']['runtime_action']['executed_invocation']
            action_name = action['arguments'].get('intent', action['skill_name']).replace('_', ' ')
            label = 'ARCHIVED RGB / ' + (f'ACTION {step+1:02d}: ' + action_name.upper() if index != 3 else 'STATE OBSERVATION')
            note = case['model'] + (' / action-feedback intervention' if case['feedback'] != 'none' else ' / no action feedback')
        spaced(d, (96, 318), label, MUTED, 16, 1)
        im.paste(picture, (96, 363)); d = ImageDraw.Draw(im)
        d.rectangle((95, 362, 736, 843), outline=LINE, width=1)
        text(d, (96, 866), note, 21, MUTED)
        if index == 0:
            # Editorial pointer identifies the pictured chair, not a recorded click.
            x, y = 96+400, 363+330; radius = 20 + 12 * (1 - (t % 1))
            d.ellipse((x-radius, y-radius, x+radius, y+radius), outline=TEAL, width=3)
            text(d, (96, 805), 'Illustrative pointer', 20, WHITE)
        spaced(d, (880, 345), 'EXAMPLE TASK', col, 19, 2)
        text(d, (876, 388), f['task'], 39, WHITE, 'serif')
        text(d, (882, 475), f['condition'], 37, WHITE, spacing=12)
        d.line((880, 604, 1835, 604), fill=LINE, width=1)
        spaced(d, (880, 631), 'WHAT THIS TESTS', col, 18, 2)
        text(d, (880, 675), f['goal'], 33, MUTED, spacing=12)
        n = len(f['stages']); width = (948 - (n-1)*14) / n
        for j, label in enumerate(f['stages']):
            x = 880 + j*(width+14); on = j <= min(n-1, int(t/7*n))
            d.rounded_rectangle((x, 805, x+width, 865), 7, fill=PANEL, outline=col if on else LINE, width=2)
            text(d, (x+18, 820), label, 25, col if on else MUTED)
        self.family_strip(d, index, t)
        return im

    @staticmethod
    def demo_state(demo, t):
        """Editorial clock over all source actions, including failed attempts."""
        elapsed = max(0, t - demo['reset'])
        reset = t < demo['reset']
        for index, seconds in enumerate(demo['action_seconds']):
            if elapsed < seconds:
                phase = elapsed / seconds
                after = phase >= .45
                return index, after, phase, reset
            elapsed -= seconds
        return len(demo['action_seconds']) - 1, True, 1.0, False

    @staticmethod
    def action_label(action):
        args = action['arguments']; skill = action['skill_name']
        if skill == 'navigate':
            names = {'forward': 'Move forward', 'backward': 'Move backward',
                     'turn_left': 'Turn left', 'turn_right': 'Turn right'}
            return names[args['mode']], f"magnitude: {args['magnitude']}"
        if skill == 'look':
            return 'Look ' + args['direction'], f"pitch: {args['magnitude']} degrees"
        if skill == 'report':
            return 'Report', 'status: ' + args['status']
        return args['intent'].replace('_', ' ').capitalize(), f"executed pixel: ({args['x']}, {args['y']})"

    def demo(self, number, t):
        spec = DEMOS[number]; cid = spec['case']; case = self.cases[cid]
        index, after, phase, reset = self.demo_state(spec, t)
        rows = case['trace']['steps']; row = rows[index]
        action = row['metadata']['runtime_action']['executed_invocation']
        done = index == len(rows)-1 and after
        if cid == 'post-goal-kettle' and index == 8:
            return self.kettle_change(after)
        im,d = self.base(9+number)
        text(d,(78,142),spec['title'],62,WHITE,'serif')
        feedback = 'NO ACTION FEEDBACK' if case['feedback']=='none' else 'ACTION-FEEDBACK INTERVENTION'
        text(d,(84,239),case['model'] + ' / ' + feedback,27,TEAL if case['feedback']=='none' else CLAY)
        observation = index + int(after)
        label = 'RESET / BEFORE ANY ACTION' if reset else ('AFTER' if after else 'BEFORE') + f' ACTION {index+1:02d}'
        spaced(d,(96,306),label,MUTED,18,2)
        im.paste(self.case_images[cid][observation],(96,355));d=ImageDraw.Draw(im)
        d.rectangle((95,354,736,835),outline=LINE,width=1)
        if not reset and not after and action['skill_name']=='interact_pixel':
            args=action['arguments'];x,y=96+args['x'],355+args['y'];radius=20+12*(1-phase/.45)
            d.ellipse((x-radius,y-radius,x+radius,y+radius),outline=TEAL,width=3)
            d.line((x-9,y,x+9,y),fill=WHITE,width=2);d.line((x,y-9,x,y+9),fill=WHITE,width=2)
        text(d,(96,862),'Original 640 × 480 RGB / step-sampled replay',24,MUTED)
        text(d,(96,906),'Every recorded action retained; playback is accelerated.',23,MUTED)
        spaced(d,(905,320),'TASK START' if reset else f'EXECUTED ACTION {index+1:02d} / {len(rows):02d}',MUTED,20,2)
        title, detail = ('Observe the scene','Read the instruction and the first RGB frame.') if reset else self.action_label(action)
        text(d,(902,372),title,66,WHITE,'serif')
        text(d,(908,473),detail,30,TEAL,'mono' if not reset else 'sans')
        if action['skill_name']=='report' and not reset:
            summary='\n'.join(textwrap.wrap(action['arguments'].get('summary',''),51))
            text(d,(908,533),summary,27,WHITE,spacing=10)
        elif after and not reset:
            error=row['error_type']
            outcome = error.replace('_',' ') if error else 'Action accepted by the simulator'
            text(d,(908,542),outcome,30,CLAY if error else MUTED)
        elif not reset:
            text(d,(908,542),'The action uses the displayed observation.',28,MUTED)
        d.line((906,640,1837,640),fill=LINE,width=1)
        spaced(d,(906,668),'EVALUATOR EVIDENCE / NOT MODEL INPUT',MUTED,17,1)
        world = row['judge_success'] if after else (rows[index-1]['judge_success'] if index else None)
        goal = 'awaiting action' if world is None else ('achieved' if world else 'not yet achieved')
        text(d,(906,715),'World goal: '+goal,37,TEAL if world else WHITE,'serif')
        terminal_report=done and action['skill_name']=='report'
        report = ('matched' if case['benchmark_success'] else 'mismatched') if terminal_report else 'not submitted'
        text(d,(906,783),'Terminal report: '+report,34,WHITE,'serif')
        if done:
            reason = 'SUCCESS' if case['benchmark_success'] else 'BUDGET EXHAUSTED'
            outcome = f"{reason} / W = {int(case['world_success'])}, B = {int(case['benchmark_success'])}"
            d.rounded_rectangle((904,851,1838,930),9,fill=PANEL,outline=TEAL if case['benchmark_success'] else CLAY,width=2)
            text(d,(924,876),outcome,29,TEAL if case['benchmark_success'] else CLAY,'mono')
        elif cid == 'post-goal-kettle' and world:
            extra=max(0,index+int(after)-case['first_world_step'])
            text(d,(908,869),f'{extra:02d} further actions after attainment',29,CLAY,'mono')
        count=len(rows);gap=1744/count
        for j in range(count):
            color=TEAL if j<index or (j==index and after) else LINE
            if cid=='post-goal-kettle' and j>=case['first_world_step'] and (j<index or (j==index and after)):
                color=CLAY
            d.rectangle((88+j*gap,973,88+(j+1)*gap-5,985),fill=color)
        return im

    def kettle_change(self, after):
        im,d=self.base(11)
        text(d,(78,142),'Action 09: the kettle lid opens.',65,WHITE,'serif')
        text(d,(84,239),'Qwen3.6-27B / ACTION-FEEDBACK INTERVENTION / original observations',26,CLAY)
        box=(250,330,320,400)
        for j,obs in enumerate((8,9)):
            x=80+j*1120
            spaced(d,(x,304),'BEFORE ACTION 09' if j==0 else 'AFTER ACTION 09',MUTED if j==0 else TEAL,18,1)
            if j==0 or after:
                source=self.case_images['post-goal-kettle'][obs]
                im.paste(source,(x,355));d=ImageDraw.Draw(im)
                d.rectangle((x-1,354,x+640,835),outline=LINE if j==0 else TEAL,width=1)
                d.rectangle((x+box[0],355+box[1],x+box[2],355+box[3]),outline=TEAL,width=2)
                im.paste(source.crop(box).resize((140,140),Image.Resampling.NEAREST),(x,855));d=ImageDraw.Draw(im)
                text(d,(x+165,870),'Lid closed' if j==0 else 'Lid open',33,WHITE,'serif')
                text(d,(x+165,929),'70 × 70 detail / 2× pixels',21,MUTED,'mono')
            else:
                d.rectangle((x,355,x+640,835),fill=PANEL,outline=LINE,width=1)
                text(d,(x+150,550),'Awaiting action result',30,MUTED)
        spaced(d,(785,366),'EXECUTED PIXEL',MUTED,17,1)
        text(d,(785,420),'(288, 359)',37,TEAL,'mono')
        d.line((790,510,1104,510),fill=TEAL,width=3)
        d.polygon([(1104,510),(1086,501),(1086,519)],fill=TEAL)
        text(d,(782,570),'World goal',35,WHITE,'serif')
        text(d,(784,631),'achieved' if after else 'not yet met',35,TEAL if after else MUTED,'serif')
        text(d,(785,730),'No report yet.',28,CLAY)
        text(d,(785,792),'Evaluator evidence',22,MUTED)
        return im

    def dataset(self, t):
        im, d = self.base(12)
        text(d, (76, 145), '1,000', 142, TEAL, 'serif')
        text(d, (520, 193), 'frozen evaluation episodes', 56, WHITE, 'serif')
        text(d, (84, 320), 'Balanced across capabilities', 34, WHITE)
        text(d, (84, 378), '8 families × 125 episodes', 26, MUTED, 'mono')
        for j, f in enumerate(FAMILIES):
            y = 470+j*58; col = TEAL if j < 4 else CLAY
            text(d, (86, y-3), f['code'], 28, col, 'mono')
            end = 172 + round(650*ease((t-.08*j)/1.3))
            d.rounded_rectangle((172, y, max(173, end), y+29), 3, fill=col)
            text(d, (850, y-2), '125', 26, WHITE, 'mono')
        d.line((1045, 365, 1045, 934), fill=LINE, width=1)
        for j,(number, name, detail, color) in enumerate([
            (self.facts['platform_episodes']['ithor'], 'iTHOR', 'Built-in indoor scenes', TEAL),
            (self.facts['platform_episodes']['procthor'], 'ProcTHOR', 'Procedural house specifications', CLAY)]):
            y = 411+j*270
            text(d, (1130, y), str(number), 105, color, 'serif')
            text(d, (1450, y+20), name, 48, WHITE, 'serif')
            text(d, (1135, y+145), detail, 27, MUTED)
        text(d, (84, 970), 'Episode definitions, task instructions, budgets and deterministic goal predicates.', 26, MUTED)
        return im

    def layout(self, d, house, box, active):
        x,y,w,h = box
        points = [p for room in house['rooms'] for p in room['floorPolygon']]
        xs,zs = [p['x'] for p in points], [p['z'] for p in points]
        scale = min((w-36)/(max(xs)-min(xs)), (h-36)/(max(zs)-min(zs)))
        dx=x+(w-(max(xs)-min(xs))*scale)/2;dy=y+(h-(max(zs)-min(zs))*scale)/2
        for room in house['rooms']:
            color = self.room_colors[room['roomType']]
            polygon = [(dx+(p['x']-min(xs))*scale, dy+(p['z']-min(zs))*scale) for p in room['floorPolygon']]
            fill = mix(PANEL, color, .50 if room['roomType'] == active else .18)
            d.polygon(polygon, fill=fill, outline=color, width=2)

    def scenes(self, t):
        im,d=self.base(13)
        text(d,(80,145),'69',100,TEAL,'serif');text(d,(245,185),'iTHOR scene names',43,WHITE,'serif')
        text(d,(1025,145),'465',100,CLAY,'serif');text(d,(1270,185),'ProcTHOR houses',43,WHITE,'serif')
        types=list(self.room_colors);active=types[min(3,int(t/2.5))]
        for j,name in enumerate(types):
            x=90+j*445;label='Living room' if name=='LivingRoom' else name
            d.ellipse((x,308,x+18,326),fill=self.room_colors[name])
            text(d,(x+34,298),label,29,WHITE if name==active else MUTED)
        for j,house in enumerate(self.layouts):
            x=80+(j%3)*597;y=373+(j//3)*270
            d.rounded_rectangle((x,y,x+565,y+244),10,fill=PANEL,outline=LINE,width=1)
            self.layout(d,house,(x+10,y+8,545,225),active)
        text(d,(85,936),'Selected actual ProcTHOR floor polygons / evaluator-side assets, never model input',23,MUTED)
        text(d,(85,977),'Counts refer to scene identifiers and house specifications, not unique floor-plan geometries.',23,MUTED)
        return im

    def metrics(self, t):
        im,d=self.base(14)
        text(d,(77,146),'Doing the task. Reporting it correctly.',65,WHITE,'serif')
        text(d,(84,252),'Two outcomes evaluated at episode closure',31,MUTED)
        cid='post-goal-kettle';im.paste(self.case_images[cid][-1],(96,384));d=ImageDraw.Draw(im)
        spaced(d,(96,336),'ARCHIVED EXAMPLE / FINAL OBSERVATION',MUTED,17,1)
        text(d,(96,890),'Lid opened. Budget exhausted. No report.',28,WHITE,'serif')
        text(d,(96,943),'Qwen3.6-27B / action-feedback intervention',22,MUTED)
        for j,(symbol,title,definition,col) in enumerate([
            ('W','World completion','Is the final semantic task goal satisfied?',TEAL),
            ('B','Benchmark success','W = 1 and a terminal report with matching status',CLAY)]):
            y=345+j*225
            text(d,(890,y),symbol,94,col,'serif');text(d,(1020,y+13),title,42,WHITE,'serif')
            text(d,(1020,y+88),definition,28,MUTED)
        d.rounded_rectangle((892,802,1838,970),10,fill=PANEL,outline=LINE,width=1)
        text(d,(918,822),'Example: W = 1, B = 0',37,TEAL,'mono')
        text(d,(920,888),'Gap = mean W − mean B',33,WHITE,'serif')
        text(d,(920,939),'Achieved goals without correct terminal commitment',24,MUTED)
        return im

    def failures(self, t):
        im,d=self.base(15)
        text(d,(78,145),'Why did the episode end?',71,WHITE,'serif')
        rows=[('FR','False report','The submitted status\ncontradicts the world\nor expected state label.',CLAY),
              ('NR','No report','The step budget\nexpires without\na terminal report.',TEAL),
              ('IL','Invalid-action limit','Repeated invalid actions\nreach the limit and\nforce termination.',(165,170,222))]
        active=min(2,int(t/3))
        for j,(code,name,detail,col) in enumerate(rows):
            x=80+j*598
            d.rounded_rectangle((x,325,x+562,834),12,fill=PANEL,outline=col if j==active else LINE,width=3 if j==active else 1)
            text(d,(x+32,360),code,112,col,'serif')
            text(d,(x+34,532),name,38,WHITE,'serif')
            text(d,(x+34,622),detail,31,MUTED,spacing=18)
        text(d,(85,894),'Interpret W, B, gap, FR, NR and IL together.',37,WHITE,'serif')
        text(d,(86,963),'A small gap alone does not establish reliable task-state judgment.',27,MUTED)
        return im

    def ending(self, t):
        im,d=self.base(16)
        spaced(d,(84,169),'THE QUESTION BEHIND VIGIL',TEAL,21,3)
        text(d,(74,258),'Did it finish?',113,WHITE,'serif')
        text(d,(74,412),'Did it report correctly?',104,WHITE,'serif')
        d.line((84,596,1837,596),fill=TEAL,width=2)
        text(d,(86,651),'1,000 episodes  /  8 task families  /  iTHOR + ProcTHOR',39,WHITE,'serif')
        text(d,(88,739),'First-person RGB. Explicit reports. Deterministic evaluation.',33,MUTED)
        text(d,(88,828),'World completion and terminal commitment, measured separately.',31,TEAL)
        self.family_strip(d,7,7)
        return im

    def frame(self, t):
        i=max(j for j,start in enumerate(STARTS) if t>=start);local=t-STARTS[i]
        if i==0:im=self.title(local)
        elif i<=8:im=self.family(i-1,local)
        elif i<=11:im=self.demo(i-9,local)
        else:im={12:self.dataset,13:self.scenes,14:self.metrics,15:self.failures,16:self.ending}[i](local)
        d=ImageDraw.Draw(im)
        caption=next((s for a,b,s in SUBTITLES if a<=t<b),'')
        if caption:
            width=d.textlength(caption,font=font(26))
            if width>W-100:raise ValueError('Caption too wide')
            d.rectangle((0,1018,W,1075),fill=INK)
            text(d,((W-width)/2,1030),caption,26,WHITE)
        d.rectangle((0,H-4,W,H),fill=LINE);d.rectangle((0,H-4,round(W*t/DURATION),H),fill=TEAL)
        if t<.6:im=Image.blend(Image.new('RGB',(W,H),INK),im,ease(t/.6))
        if t>DURATION-.8:im=Image.blend(im,Image.new('RGB',(W,H),INK),(t-(DURATION-.8))/.8)
        return im


def score_audio(path):
    """Original quiet sine/triangle ambient score; no sampled or licensed audio."""
    sr = 48000
    samples = np.zeros((DURATION*sr, 2), dtype=np.float32)
    rng = np.random.default_rng(42)
    chords = [(48, 55, 60, 64), (45, 52, 59, 64), (41, 48, 57, 60), (43, 50, 57, 62)]
    for j, begin in enumerate(np.arange(0, DURATION, 4.0)):
        length = min(7.5, DURATION-begin)
        t = np.arange(round(length*sr), dtype=np.float32)/sr
        env = np.minimum(t/1.3, 1.0)*np.exp(-t/.95)*.024
        pad = np.minimum(t/2.0, 1.0)*np.minimum((length-t)/2.5, 1.0)*.008
        for k, midi in enumerate(chords[(j//2)%4]):
            hz = 440*2**((midi-69)/12)
            phase = rng.uniform(0, math.tau)
            tone = np.sin(math.tau*hz*t+phase)*pad
            tone += (np.sin(math.tau*hz*2*t)+.17*np.sin(math.tau*hz*4*t))*env
            pan = .2 + k*.2
            start = round(begin*sr)
            samples[start:start+len(t), 0] += tone*math.sqrt(1-pan)
            samples[start:start+len(t), 1] += tone*math.sqrt(pan)
    fade = np.minimum(np.arange(len(samples))/sr/3, 1)*np.minimum((len(samples)-np.arange(len(samples)))/sr/4, 1)
    samples *= fade[:, None] * 3.0
    pcm = (np.clip(samples, -1, 1)*32767).astype('<i2')
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(2); out.setsampwidth(2); out.setframerate(sr); out.writeframes(pcm.tobytes())


def timestamp(t):
    seconds = int(t)
    return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}.{round((t-seconds)*1000):03}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets-dir', type=Path, default=ROOT/'docs/media/source')
    parser.add_argument('--out-dir', type=Path, default=ROOT/'docs/media')
    parser.add_argument('--preview-only', action='store_true')
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    film = Film(args.assets_dir)
    # Poster matches the introduction, with a visible play affordance.
    poster = film.frame(2.8)
    d = ImageDraw.Draw(poster)
    d.ellipse((1700, 906, 1790, 996), fill=WHITE)
    d.polygon([(1734, 928), (1734, 975), (1770, 951)], fill=INK)
    poster.save(args.out_dir/'overview-poster.jpg', quality=96, subsampling=0)
    preview_times = [2.8] + [start+4.5 for start in STARTS[1:]]
    contact = Image.new('RGB', (1440, ((len(preview_times)+1)//2)*405), PAPER)
    for j, when in enumerate(preview_times):
        contact.paste(film.frame(when).resize((720, 405), Image.Resampling.LANCZOS), ((j%2)*720, (j//2)*405))
    if args.preview_only:
        contact.save(args.out_dir/'storyboard.jpg', quality=92)
        return
    vtt = 'WEBVTT\n\n' + '\n\n'.join(f'{timestamp(a)} --> {timestamp(b)}\n{s}' for a,b,s in SUBTITLES)+'\n'
    (args.out_dir/'overview.en.vtt').write_text(vtt)
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix='vigil-film-') as temp:
        temp = Path(temp); audio = temp/'score.wav'; score_audio(audio)
        cmd = [ffmpeg,'-hide_banner','-loglevel','warning','-y','-f','rawvideo','-vcodec','rawvideo',
               '-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-i',str(audio),
               '-c:v','libx264','-preset','slow','-crf','17','-threads','4','-pix_fmt','yuv420p',
               '-c:a','aac','-b:a','128k','-movflags','+faststart','-shortest',str(args.out_dir/'overview.mp4')]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for n in range(DURATION*FPS):
                proc.stdin.write(film.frame(n/FPS).tobytes())
                if n % (FPS*8) == 0:
                    print(f'Rendered {n/FPS:.0f}/{DURATION}s', flush=True)
            proc.stdin.close()
            if proc.wait():
                raise RuntimeError('Video encoder failed')
        except BaseException:
            proc.kill(); proc.wait(); raise
        # One complete recorded task, including its final report, for the README.
        cuts = '[0:v]trim=61:73,setpts=PTS-STARTPTS,fps=8,scale=960:-2:flags=lanczos,split[v][colors];[colors]palettegen=max_colors=256[p];[v][p]paletteuse=dither=bayer:bayer_scale=3[out]'
        # Generate directly from the finished film, without a second lossy
        # H.264 intermediate. The full-resolution film remains available separately.
        subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(args.out_dir/'overview.mp4'),'-filter_complex',cuts,'-map','[out]','-an','-loop','0','-threads','4',str(args.out_dir/'overview-preview.gif')],check=True)
    print('Created overview.mp4, overview-preview.gif, overview-poster.jpg and English captions.', flush=True)


if __name__ == '__main__':
    main()
