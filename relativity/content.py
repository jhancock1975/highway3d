"""Lecture content: what is said, and what is on screen while it is said.

Each segment carries narration text and a visual spec. Timing is not written
here -- it comes from the length of the synthesised speech, so the picture
always matches the voice rather than the other way round.

The physics is standard special relativity, in the order it is usually taught:
the conflict between Galilean relativity and electromagnetism, the two
postulates, then simultaneity, time dilation, length contraction, the Lorentz
transformation, velocity addition, the invariant interval, mass-energy, and
the experimental evidence.
"""

# Visual kinds the renderer understands:
#   title    -- chapter card
#   math     -- one or more LaTeX lines, revealed in order
#   diagram  -- a named diagram, drawn by visuals.py
#   bullets  -- short lines of plain text

CHAPTERS = [
    # ---------------------------------------------------------------- opening
    dict(
        title="A Problem Nobody Wanted",
        segments=[
            dict(
                text="Let me begin with a disagreement. By the end of the "
                     "nineteenth century, physics rested on two pillars, and "
                     "each one worked beautifully. The trouble was that they "
                     "could not both be right.",
                visual=dict(kind="title", main="Special Relativity",
                            sub="a problem nobody wanted"),
            ),
            dict(
                text="The first pillar was mechanics, in the form Galileo and "
                     "Newton left it. The second was electromagnetism, in the "
                     "form James Clerk Maxwell left it. Put them side by side "
                     "and they contradict each other about something very "
                     "simple: how fast light travels.",
                visual=dict(kind="bullets", heading="Two pillars",
                            items=["Galilean mechanics",
                                   "Maxwell's electromagnetism",
                                   "They disagree about light"]),
            ),
            dict(
                text="Resolving that contradiction does not require difficult "
                     "mathematics. It requires giving up an assumption so "
                     "deeply held that almost nobody noticed they were making "
                     "it. The assumption is that time is universal.",
                visual=dict(kind="bullets", heading="The assumption to drop",
                            items=["Time is the same for everyone",
                                   "Simultaneity is absolute",
                                   "Neither survives"]),
            ),
        ],
    ),

    # ------------------------------------------------------ galilean relativity
    dict(
        title="Galileo's Ship",
        segments=[
            dict(
                text="Galileo asked you to imagine yourself below deck on a "
                     "ship moving smoothly over a calm sea. Fish swim in their "
                     "bowl. Drops fall from a bottle into a jar beneath. You "
                     "throw something to a friend. Nothing you can do inside "
                     "that cabin will tell you whether the ship is moving or "
                     "standing still.",
                visual=dict(kind="diagram", name="galileo_ship"),
            ),
            dict(
                text="That is the principle of relativity, and it is older "
                     "than I am by three centuries. The laws of mechanics are "
                     "the same in every frame of reference that moves at "
                     "constant velocity. There is no experiment that picks out "
                     "one such frame as truly at rest.",
                visual=dict(kind="math", heading="The principle of relativity",
                            lines=[r"$F = ma \quad$ holds in every inertial frame",
                                   r"no experiment finds absolute rest"]),
            ),
            dict(
                text="To move between two such frames, Galileo gives you a "
                     "simple recipe. If your frame moves at speed v along the "
                     "x axis relative to mine, then positions shift by v times "
                     "t, and time is simply carried across unchanged.",
                visual=dict(kind="math", heading="Galilean transformation",
                            lines=[r"$x' = x - vt$",
                                   r"$y' = y, \quad z' = z$",
                                   r"$t' = t$"]),
            ),
            dict(
                text="Look carefully at that last line. t prime equals t. It "
                     "looks like bookkeeping, almost too obvious to write "
                     "down. It is in fact the whole problem, and everything "
                     "that follows comes from taking it seriously enough to "
                     "doubt it.",
                visual=dict(kind="math", heading="The line that fails",
                            lines=[r"$t' = t$",
                                   r"time, assumed universal",
                                   r"this is the assumption that breaks"]),
            ),
            dict(
                text="One immediate consequence of Galileo's recipe is that "
                     "velocities simply add. Walk forward at four kilometres "
                     "an hour on a train doing a hundred, and the ground sees "
                     "you doing a hundred and four. Nothing could be more "
                     "natural.",
                visual=dict(kind="math", heading="Velocities add",
                            lines=[r"$u' = u - v$",
                                   r"$100 + 4 = 104 \ \mathrm{km/h}$"]),
            ),
        ],
    ),

    # ------------------------------------------------------------ maxwell
    dict(
        title="What Maxwell Found",
        segments=[
            dict(
                text="Now the second pillar. Maxwell collected the laws of "
                     "electricity and magnetism into four equations, and then "
                     "did something remarkable with them. He combined them, "
                     "and out fell a wave.",
                visual=dict(kind="math", heading="Maxwell's equations",
                            lines=[r"$\nabla \cdot \mathbf{E} = \rho/\epsilon_0$",
                                   r"$\nabla \cdot \mathbf{B} = 0$",
                                   r"$\nabla \times \mathbf{E} = -\partial \mathbf{B}/\partial t$",
                                   r"$\nabla \times \mathbf{B} = \mu_0 \mathbf{J} + \mu_0\epsilon_0 \, \partial \mathbf{E}/\partial t$"]),
            ),
            dict(
                text="The wave travelled at a speed built entirely out of two "
                     "constants you could measure on a laboratory bench, with "
                     "no light involved at all. One from electrostatics, one "
                     "from magnetism. Put them together and you get three "
                     "hundred thousand kilometres per second.",
                visual=dict(kind="math", heading="A speed from the bench",
                            lines=[r"$c = \dfrac{1}{\sqrt{\mu_0 \epsilon_0}}$",
                                   r"$c \approx 3.00 \times 10^8 \ \mathrm{m/s}$"]),
            ),
            dict(
                text="That is the measured speed of light. Maxwell had shown "
                     "that light is an electromagnetic wave. A triumph. But "
                     "notice what his equations do not contain: they do not "
                     "say what that speed is measured relative to.",
                visual=dict(kind="bullets", heading="The awkward question",
                            items=["c falls out of the equations",
                                   "Relative to what?",
                                   "The equations do not say"]),
            ),
            dict(
                text="Every other wave physics knew travelled through "
                     "something. Sound travels through air, at a fixed speed "
                     "relative to the air. So it was natural to suppose light "
                     "travels through a medium too. It was given a name: the "
                     "luminiferous ether.",
                visual=dict(kind="bullets", heading="The ether",
                            items=["Sound moves through air",
                                   "Waves on water move through water",
                                   "So light moves through ... ether?"]),
            ),
            dict(
                text="If the ether exists, the Earth must move through it, and "
                     "light should appear faster or slower depending on which "
                     "way you look. Michelson and Morley built an instrument "
                     "delicate enough to detect that difference. They found "
                     "nothing. Not a small effect. Nothing.",
                visual=dict(kind="diagram", name="michelson"),
            ),
        ],
    ),

    # ---------------------------------------------------------- the postulates
    dict(
        title="Two Postulates",
        segments=[
            dict(
                text="So here is the choice. Either the principle of "
                     "relativity is wrong, or Maxwell is wrong, or something "
                     "we assumed about space and time is wrong. My proposal "
                     "was to keep both pillars, and give up the assumption.",
                visual=dict(kind="bullets", heading="Something has to give",
                            items=["Keep relativity",
                                   "Keep Maxwell",
                                   "Give up universal time"]),
            ),
            dict(
                text="The first postulate: the laws of physics take the same "
                     "form in every inertial frame. Not just mechanics, as "
                     "Galileo said, but all of physics, electromagnetism "
                     "included.",
                visual=dict(kind="math", heading="First postulate",
                            lines=[r"The laws of physics are the same",
                                   r"in every inertial frame."]),
            ),
            dict(
                text="The second postulate: light travels through empty space "
                     "at the speed c, and that speed does not depend on the "
                     "motion of the source, nor on the motion of whoever is "
                     "measuring it.",
                visual=dict(kind="math", heading="Second postulate",
                            lines=[r"$c$ is the same in every inertial frame",
                                   r"independent of the motion of source",
                                   r"or of observer"]),
            ),
            dict(
                text="Read the second postulate again, because it is genuinely "
                     "strange. Chase a beam of light at nine tenths of c, and "
                     "you might expect it to crawl away from you at a tenth of "
                     "c. It does not. It recedes at the full c. Everyone who "
                     "measures it gets the same number.",
                visual=dict(kind="diagram", name="chase_light"),
            ),
            dict(
                text="Everything else I am going to show you is a consequence "
                     "of those two statements. No new forces, no hidden "
                     "mechanism. Just the refusal to let go of either "
                     "postulate, and the willingness to let time bend instead.",
                visual=dict(kind="bullets", heading="Everything follows",
                            items=["Simultaneity is relative",
                                   "Moving clocks run slow",
                                   "Moving lengths contract",
                                   "E = mc squared"]),
            ),
        ],
    ),

    # -------------------------------------------------------- simultaneity
    dict(
        title="Simultaneity Comes Apart",
        segments=[
            dict(
                text="Start with the idea that breaks first. Two events happen "
                     "at the same time. That sounds like a plain fact about "
                     "the world. It is not. It is a fact about you.",
                visual=dict(kind="title", main="Relativity of Simultaneity",
                            sub="the first casualty"),
            ),
            dict(
                text="Picture a railway carriage moving down the track, with a "
                     "lamp exactly at its centre. The lamp flashes once. The "
                     "light spreads out in both directions at speed c.",
                visual=dict(kind="diagram", name="train_flash_inside"),
            ),
            dict(
                text="A passenger sitting in the carriage sees the light reach "
                     "the front wall and the back wall at the same moment. Of "
                     "course she does. The lamp is midway between them, and "
                     "light travels at the same speed each way.",
                visual=dict(kind="diagram", name="train_flash_inside"),
            ),
            dict(
                text="Now watch the same flash from the embankment. While the "
                     "light is in flight, the carriage moves. The back wall "
                     "advances to meet the light going backwards. The front "
                     "wall runs away from the light chasing it.",
                visual=dict(kind="diagram", name="train_flash_outside"),
            ),
            dict(
                text="And since light travels at c for me too, not at c plus "
                     "or minus the speed of the train, the light reaches the "
                     "back wall first. The passenger says the two events were "
                     "simultaneous. I say the back one happened earlier. "
                     "Neither of us is mistaken.",
                visual=dict(kind="diagram", name="train_flash_outside"),
            ),
            dict(
                text="There is no fact of the matter about which events happen "
                     "at the same time. Simultaneity depends on your state of "
                     "motion. Once you accept that, the rest of relativity is "
                     "almost forced upon you.",
                visual=dict(kind="math", heading="Simultaneity is frame-dependent",
                            lines=[r"$\Delta t = 0 \ $ in one frame",
                                   r"$\Delta t' \neq 0 \ $ in another",
                                   r"$\Delta t' = -\gamma \, v \, \Delta x / c^2$"]),
            ),
        ],
    ),

    # -------------------------------------------------------- time dilation
    dict(
        title="The Light Clock",
        segments=[
            dict(
                text="Now let me build the simplest clock I can, and see what "
                     "the postulates do to it. Two mirrors facing each other, "
                     "a fixed distance L apart, with a pulse of light bouncing "
                     "between them. Each bounce is a tick.",
                visual=dict(kind="diagram", name="light_clock_rest"),
            ),
            dict(
                text="At rest, the light goes straight up and straight down. "
                     "The round trip covers two L at speed c, so one tick "
                     "takes two L over c. Nothing surprising yet.",
                visual=dict(kind="math", heading="Clock at rest",
                            lines=[r"$\Delta t_0 = \dfrac{2L}{c}$"]),
            ),
            dict(
                text="Now set that same clock moving sideways at speed v, and "
                     "watch it go past. The light still leaves the bottom "
                     "mirror and arrives at the top one. But in the time it "
                     "takes, the whole clock has shifted along. So the path I "
                     "see is not vertical. It is a diagonal.",
                visual=dict(kind="diagram", name="light_clock_moving"),
            ),
            dict(
                text="The diagonal is longer than the vertical. That is simple "
                     "geometry. And here the second postulate does its work: I "
                     "am not allowed to say the light goes faster to cover the "
                     "extra distance. It goes at c, the same c. A longer path "
                     "at the same speed takes more time.",
                visual=dict(kind="diagram", name="light_clock_moving"),
            ),
            dict(
                text="Let us do the arithmetic, because it takes only a line. "
                     "In my frame one tick takes delta t. In that time the "
                     "clock moves v delta t sideways, while the light covers c "
                     "delta t along the diagonal. Half a tick, and Pythagoras "
                     "gives the rest.",
                visual=dict(kind="math", heading="Pythagoras on the diagonal",
                            lines=[r"$\left(\dfrac{c \, \Delta t}{2}\right)^{2} = L^{2} + \left(\dfrac{v \, \Delta t}{2}\right)^{2}$"]),
            ),
            dict(
                text="Gather the delta t terms on one side, and out comes the "
                     "answer. The moving clock's tick is longer than the "
                     "resting clock's tick, by a factor that depends only on "
                     "the speed.",
                visual=dict(kind="math", heading="Solving for the tick",
                            lines=[r"$\Delta t^{2}\left(c^{2} - v^{2}\right) = 4L^{2}$",
                                   r"$\Delta t = \dfrac{2L}{c}\dfrac{1}{\sqrt{1 - v^{2}/c^{2}}}$",
                                   r"$\Delta t = \gamma \, \Delta t_0$"]),
            ),
            dict(
                text="That factor deserves its own name. We call it gamma, the "
                     "Lorentz factor. It is one when nothing is moving, it "
                     "creeps above one as speed increases, and it runs away to "
                     "infinity as v approaches c.",
                visual=dict(kind="diagram", name="gamma_curve"),
            ),
            dict(
                text="At a tenth of the speed of light, gamma is about one "
                     "point zero zero five. At nine tenths, it is about two "
                     "point three. At ninety-nine per cent, about seven. The "
                     "effect hides at everyday speeds and becomes overwhelming "
                     "near c.",
                visual=dict(kind="math", heading="How gamma grows",
                            lines=[r"$v = 0.10c \ \Rightarrow \ \gamma \approx 1.005$",
                                   r"$v = 0.90c \ \Rightarrow \ \gamma \approx 2.29$",
                                   r"$v = 0.99c \ \Rightarrow \ \gamma \approx 7.09$"]),
            ),
            dict(
                text="And note what this is not. It is not that the clock is "
                     "damaged by its motion, or that the mechanism is "
                     "disturbed. Any clock whatever gives the same answer, "
                     "because it is time itself that is being measured "
                     "differently. Including, if you are the one moving, your "
                     "heartbeat.",
                visual=dict(kind="bullets", heading="Not a mechanical effect",
                            items=["Every clock agrees",
                                   "Nothing is disturbed",
                                   "Time itself is frame-dependent"]),
            ),
        ],
    ),

    # ------------------------------------------------------ length contraction
    dict(
        title="Lengths Shrink",
        segments=[
            dict(
                text="If time is affected, length cannot escape. Suppose you "
                     "wish to measure a moving rod. You must mark where both "
                     "ends are at the same moment. But we have just seen that "
                     "at the same moment is not something everyone agrees on.",
                visual=dict(kind="diagram", name="rod_contraction"),
            ),
            dict(
                text="Work it through and the result is the mirror image of "
                     "time dilation. A rod of length L nought in its own rest "
                     "frame is measured shorter, by exactly the same gamma, "
                     "when it moves past you.",
                visual=dict(kind="math", heading="Length contraction",
                            lines=[r"$L = \dfrac{L_0}{\gamma} = L_0\sqrt{1 - v^{2}/c^{2}}$"]),
            ),
            dict(
                text="Only along the direction of motion, mind. The rod is not "
                     "squeezed from all sides. Its height and width are "
                     "untouched. Space contracts along the line of travel and "
                     "nowhere else.",
                visual=dict(kind="math", heading="Only along the motion",
                            lines=[r"$L_x = L_{x,0}/\gamma$",
                                   r"$L_y = L_{y,0}, \quad L_z = L_{z,0}$"]),
            ),
        ],
    ),

    # ------------------------------------------------------ lorentz transform
    dict(
        title="The Lorentz Transformation",
        segments=[
            dict(
                text="We are ready to replace Galileo's recipe. We need a way "
                     "of converting one observer's coordinates into another's "
                     "that keeps the speed of light the same for both. Lorentz "
                     "found the formulae; the postulates tell us why they are "
                     "the right ones.",
                visual=dict(kind="math", heading="Replacing Galileo",
                            lines=[r"$x' = \gamma\left(x - vt\right)$",
                                   r"$y' = y, \quad z' = z$",
                                   r"$t' = \gamma\left(t - \dfrac{vx}{c^{2}}\right)$"]),
            ),
            dict(
                text="Compare that with what we had before. The space equation "
                     "has picked up a factor of gamma. But look at the time "
                     "equation, which used to read t prime equals t. It now "
                     "contains a term in x.",
                visual=dict(kind="math", heading="Then and now",
                            lines=[r"Galileo: $\quad t' = t$",
                                   r"Lorentz: $\quad t' = \gamma\left(t - vx/c^{2}\right)$"]),
            ),
            dict(
                text="That term is the whole of relativity in one place. Your "
                     "time depends on where you are, not only on when. Two "
                     "clocks that I say are synchronised, separated along the "
                     "direction of motion, are not synchronised for you. Space "
                     "and time have stopped being separate.",
                visual=dict(kind="math", heading="Where the strangeness lives",
                            lines=[r"$-\dfrac{v x}{c^{2}}$",
                                   r"time depends on position"]),
            ),
            dict(
                text="And when v is small compared with c, that term becomes "
                     "negligible and gamma becomes one, and the whole thing "
                     "collapses back into Galileo's recipe. Which is why "
                     "nobody noticed for three hundred years.",
                visual=dict(kind="math", heading="Low speeds recover Galileo",
                            lines=[r"$v \ll c \ \Rightarrow \ \gamma \to 1, \quad vx/c^{2} \to 0$",
                                   r"$x' \to x - vt, \quad t' \to t$"]),
            ),
        ],
    ),

    # ------------------------------------------------------ velocity addition
    dict(
        title="Velocities Stop Adding",
        segments=[
            dict(
                text="Now we can settle the question we started with. On the "
                     "train, walking forward, Galileo said the speeds simply "
                     "add. With the Lorentz transformation they do not.",
                visual=dict(kind="math", heading="Relativistic velocity addition",
                            lines=[r"$w = \dfrac{u + v}{1 + \dfrac{uv}{c^{2}}}$"]),
            ),
            dict(
                text="At walking pace the correction is far too small to "
                     "notice, and the old rule is perfectly good. But the "
                     "denominator changes everything at high speed. Take two "
                     "velocities each of three quarters of c.",
                visual=dict(kind="math", heading="Two large velocities",
                            lines=[r"$u = v = 0.75c$",
                                   r"$\text{Galileo:} \quad 1.50c$",
                                   r"$\text{Lorentz:} \quad w = \dfrac{1.5c}{1 + 0.5625} = 0.96c$"]),
            ),
            dict(
                text="Below c, as it must be. And if you put u equal to c "
                     "itself, the formula returns c exactly, whatever v you "
                     "choose. The second postulate is not an extra rule bolted "
                     "on. It is built into the arithmetic.",
                visual=dict(kind="math", heading="Light stays at c",
                            lines=[r"$u = c \ \Rightarrow \ w = \dfrac{c + v}{1 + v/c} = c$"]),
            ),
        ],
    ),

    # ------------------------------------------------------ spacetime interval
    dict(
        title="What Everyone Agrees On",
        segments=[
            dict(
                text="So far I have taken things away from you. Lengths, "
                     "durations, simultaneity: all of them depend on who is "
                     "asking. Let me give you something back. There is a "
                     "quantity everyone agrees on.",
                visual=dict(kind="title", main="The Invariant Interval",
                            sub="something absolute after all"),
            ),
            dict(
                text="Take two events. Compute the square of the distance "
                     "between them, and subtract c squared times the square of "
                     "the time between them. That combination has the same "
                     "value in every inertial frame.",
                visual=dict(kind="math", heading="The spacetime interval",
                            lines=[r"$s^{2} = \Delta x^{2} + \Delta y^{2} + \Delta z^{2} - c^{2}\Delta t^{2}$",
                                   r"the same in every inertial frame"]),
            ),
            dict(
                text="Minkowski, who had been my mathematics teacher and was "
                     "not always impressed by me, saw what this meant before I "
                     "did. Space and time are not two things that interfere "
                     "with one another. They are one thing, and the interval "
                     "is how you measure distance in it.",
                visual=dict(kind="bullets", heading="Minkowski's reading",
                            items=["Not space and time",
                                   "One four-dimensional spacetime",
                                   "The interval is its geometry"]),
            ),
            dict(
                text="The minus sign in front of the time term is what makes "
                     "this geometry unlike the one you learned at school. It "
                     "is also what separates cause from coincidence: whether "
                     "one event can influence another depends on the sign of s "
                     "squared.",
                visual=dict(kind="diagram", name="light_cone"),
            ),
        ],
    ),

    # ------------------------------------------------------------ mass-energy
    dict(
        title="Mass and Energy",
        segments=[
            dict(
                text="One more consequence, and it is the one that escaped the "
                     "physics journals. Ask how much energy it takes to "
                     "accelerate a body, and relativity gives an answer that "
                     "grows without limit as the speed approaches c.",
                visual=dict(kind="math", heading="Energy of a moving body",
                            lines=[r"$E = \gamma m c^{2} = \dfrac{m c^{2}}{\sqrt{1 - v^{2}/c^{2}}}$"]),
            ),
            dict(
                text="That is why nothing with mass reaches the speed of "
                     "light. Not because the engine is not powerful enough, "
                     "but because the energy required runs to infinity. The "
                     "speed of light is not a practical limit. It is a "
                     "structural one.",
                visual=dict(kind="diagram", name="energy_curve"),
            ),
            dict(
                text="Now set the speed to zero and see what is left. Gamma "
                     "becomes one, and the energy does not go to zero. A body "
                     "at rest, doing nothing at all, still has energy m c "
                     "squared.",
                visual=dict(kind="math", heading="At rest",
                            lines=[r"$v = 0 \ \Rightarrow \ \gamma = 1$",
                                   r"$E_0 = m c^{2}$"]),
            ),
            dict(
                text="Mass is not a separate substance from energy. It is a "
                     "form of it, and c squared is merely the exchange rate. "
                     "The rate is enormous, which is why a very small amount "
                     "of mass corresponds to a very large amount of energy.",
                visual=dict(kind="math", heading="The exchange rate",
                            lines=[r"$E = mc^{2}$",
                                   r"$c^{2} \approx 9 \times 10^{16} \ \mathrm{m^2/s^2}$",
                                   r"$1\ \mathrm{gram} \approx 9 \times 10^{13}\ \mathrm{J}$"]),
            ),
            dict(
                text="This is the arithmetic behind the energy of the sun, and "
                     "behind the weapons that were built in my lifetime. I "
                     "signed a letter urging that such a weapon be understood "
                     "before others understood it first. I have thought about "
                     "that letter a great deal since.",
                visual=dict(kind="bullets", heading="Where the energy goes",
                            items=["Stellar fusion",
                                   "Nuclear fission",
                                   "The same equation"]),
            ),
        ],
    ),


    # ------------------------------------------------------------ twin paradox
    dict(
        title="The Twins",
        segments=[
            dict(
                text="Here is the objection I am asked about most, and it is a "
                     "good one. If motion is relative, and each of us sees the "
                     "other's clock running slow, then surely the situation is "
                     "symmetric and there can be no lasting difference. Let me "
                     "take it seriously.",
                visual=dict(kind="title", main="The Twin Paradox",
                            sub="is the situation really symmetric?"),
            ),
            dict(
                text="Two twins. One remains on Earth. The other travels to a "
                     "star four light years away at eight tenths of the speed "
                     "of light, turns around, and comes home. Gamma at that "
                     "speed is one and two thirds.",
                visual=dict(kind="math", heading="The journey",
                            lines=[r"$d = 4 \ \mathrm{light\ years}, \quad v = 0.8c$",
                                   r"$\gamma = 1/\sqrt{1 - 0.64} = 1.667$"]),
            ),
            dict(
                text="The Earth twin reckons the trip takes ten years. The "
                     "travelling twin's clock, running slow by gamma, records "
                     "six. They meet again and compare. The traveller really "
                     "is the younger, and not by a matter of opinion.",
                visual=dict(kind="math", heading="Who ages how much",
                            lines=[r"$t_{\mathrm{Earth}} = 2 \times 4/0.8 = 10 \ \mathrm{yr}$",
                                   r"$t_{\mathrm{travel}} = 10/\gamma = 6 \ \mathrm{yr}$"]),
            ),
            dict(
                text="So where does the symmetry break? At the turning point. "
                     "The Earth twin stays in one inertial frame throughout. "
                     "The traveller does not: to come home she must "
                     "accelerate, and in doing so she changes frames.",
                visual=dict(kind="diagram", name="twin_paths"),
            ),
            dict(
                text="And when she changes frames, her notion of which distant "
                     "events are happening now swings forward abruptly. That "
                     "is the relativity of simultaneity arriving to settle the "
                     "account. The paradox is not a paradox. It is a reminder "
                     "that the two paths through spacetime are genuinely "
                     "different.",
                visual=dict(kind="bullets", heading="The asymmetry",
                            items=["One twin stays inertial",
                                   "The other turns around",
                                   "Turning changes her 'now'",
                                   "Different paths, different ageing"]),
            ),
        ],
    ),

    # -------------------------------------------------------------- doppler
    dict(
        title="Colour and Motion",
        segments=[
            dict(
                text="You already know that an approaching whistle sounds "
                     "higher and a departing one lower. Light does the same, "
                     "but with a relativistic twist: the time dilation of the "
                     "source enters as well as its motion.",
                visual=dict(kind="math", heading="Relativistic Doppler",
                            lines=[r"$\dfrac{f_{\mathrm{obs}}}{f_{\mathrm{src}}} = \sqrt{\dfrac{1 - v/c}{1 + v/c}}$"]),
            ),
            dict(
                text="A source receding from you is shifted towards the red, "
                     "and one approaching towards the blue. This is how we "
                     "know that distant galaxies are moving away from us, and "
                     "how fast.",
                visual=dict(kind="diagram", name="doppler"),
            ),
            dict(
                text="There is also a transverse effect with no classical "
                     "counterpart at all. A source passing directly across "
                     "your line of sight, neither approaching nor receding, is "
                     "still shifted, purely because its clock runs slow. That "
                     "one is relativity and nothing else.",
                visual=dict(kind="math", heading="Transverse Doppler",
                            lines=[r"$f_{\mathrm{obs}} = f_{\mathrm{src}}/\gamma$",
                                   r"no classical analogue"]),
            ),
        ],
    ),

    # ------------------------------------------------------ momentum, barn
    dict(
        title="Momentum, and a Ladder",
        segments=[
            dict(
                text="Momentum needs repairing too. The Newtonian product of "
                     "mass and velocity is not conserved once you transform "
                     "between frames properly. The correct expression carries "
                     "the same gamma we have met throughout.",
                visual=dict(kind="math", heading="Relativistic momentum",
                            lines=[r"$\mathbf{p} = \gamma m \mathbf{v}$",
                                   r"$E^{2} = (pc)^{2} + (mc^{2})^{2}$"]),
            ),
            dict(
                text="That second line is worth pausing on. It relates energy, "
                     "momentum and mass in one statement, and it permits "
                     "something Newton could not: a particle with no mass at "
                     "all, carrying energy and momentum, moving always at c. "
                     "The photon.",
                visual=dict(kind="math", heading="A massless particle",
                            lines=[r"$m = 0 \ \Rightarrow \ E = pc$",
                                   r"travels at $c$, always"]),
            ),
            dict(
                text="Let me close the paradoxes with one more. A ladder "
                     "twenty feet long is carried at high speed into a barn "
                     "ten feet deep. Contracted, the ladder fits, and both "
                     "doors can be shut for an instant. In the ladder's own "
                     "frame, the barn is the contracted one and it cannot "
                     "possibly fit.",
                visual=dict(kind="diagram", name="ladder_barn"),
            ),
            dict(
                text="Both are right, and the resolution is the one you now "
                     "expect. The two doors shutting are not simultaneous for "
                     "the ladder. In its frame the far door opens before the "
                     "near one closes, and it passes through without ever "
                     "being enclosed.",
                visual=dict(kind="bullets", heading="Resolved the same way",
                            items=["Barn frame: both doors shut at once",
                                   "Ladder frame: they shut at different times",
                                   "No contradiction, only simultaneity"]),
            ),
            dict(
                text="One last caution. Relativity is often said to mean that "
                     "everything is relative. It means very nearly the "
                     "opposite. It identifies what is absolute: the speed of "
                     "light, the interval between events, the laws themselves. "
                     "What is relative is only the coordinates we happen to "
                     "use.",
                visual=dict(kind="bullets", heading="What is absolute",
                            items=["The speed of light",
                                   "The spacetime interval",
                                   "The form of the laws",
                                   "Only coordinates are relative"]),
            ),
        ],
    ),


    # ----------------------------------------------------------- proper time
    dict(
        title="Proper Time",
        segments=[
            dict(
                text="Let me sharpen what a clock actually measures. Draw a "
                     "worldline: the path a body traces through spacetime. "
                     "Along that path, the quantity a clock carried with the "
                     "body reads is called the proper time, and it belongs to "
                     "the path, not to the coordinates.",
                visual=dict(kind="math", heading="Proper time",
                            lines=[r"$c^{2}d\tau^{2} = c^{2}dt^{2} - dx^{2} - dy^{2} - dz^{2}$",
                                   r"$d\tau = dt/\gamma$"]),
            ),
            dict(
                text="Two observers disagree about how much coordinate time "
                     "elapsed between two events. They do not disagree about "
                     "the proper time along a given worldline. That is a "
                     "property of the journey itself.",
                visual=dict(kind="diagram", name="twin_paths"),
            ),
            dict(
                text="This is the clean way to say what happened to the twins. "
                     "They took two different paths between the same pair of "
                     "events, and the proper times along those paths differ. "
                     "It is no stranger than two roads between the same towns "
                     "having different lengths.",
                visual=dict(kind="bullets", heading="The twins, restated",
                            items=["Same start, same finish",
                                   "Different worldlines",
                                   "Different proper time",
                                   "Like two roads of different length"]),
            ),
            dict(
                text="Though there is one reversal worth noting. In ordinary "
                     "geometry the straight line is the shortest path. In "
                     "spacetime, because of that minus sign, the straight "
                     "worldline is the one with the most proper time. Staying "
                     "put ages you the most.",
                visual=dict(kind="math", heading="A reversed extremum",
                            lines=[r"Euclidean: the straight line is shortest",
                                   r"Spacetime: the straight worldline is longest",
                                   r"in proper time"]),
            ),
        ],
    ),

    # -------------------------------------------------------- worked example
    dict(
        title="Working It Through",
        segments=[
            dict(
                text="Let me put numbers to all of it, because formulae are "
                     "easy to nod along with. Take a vehicle travelling at six "
                     "tenths of the speed of light. First, gamma.",
                visual=dict(kind="math", heading="A worked example",
                            lines=[r"$v = 0.6c$",
                                   r"$\gamma = \dfrac{1}{\sqrt{1 - 0.36}} = \dfrac{1}{0.8} = 1.25$"]),
            ),
            dict(
                text="A gamma of one and a quarter. Now a journey of six light "
                     "years, as measured by someone at rest. At six tenths of "
                     "c that takes ten years of their time.",
                visual=dict(kind="math", heading="The journey, from outside",
                            lines=[r"$d = 6 \ \mathrm{ly}, \quad v = 0.6c$",
                                   r"$t = d/v = 10 \ \mathrm{years}$"]),
            ),
            dict(
                text="But the traveller's clock records that divided by gamma: "
                     "eight years. And from the traveller's own point of view "
                     "the distance was never six light years at all. It was "
                     "contracted to four point eight, covered at six tenths of "
                     "c, which is eight years. The two accounts agree, as they "
                     "must.",
                visual=dict(kind="math", heading="The same journey, inside",
                            lines=[r"$\tau = t/\gamma = 10/1.25 = 8 \ \mathrm{years}$",
                                   r"$L = 6/1.25 = 4.8 \ \mathrm{ly}$",
                                   r"$4.8 / 0.6 = 8 \ \mathrm{years} \quad \checkmark$"]),
            ),
            dict(
                text="Now the energy. To bring a one kilogram mass to that "
                     "speed costs gamma minus one, times m c squared. A "
                     "quarter of m c squared, which for one kilogram is about "
                     "two times ten to the sixteen joules.",
                visual=dict(kind="math", heading="The cost in energy",
                            lines=[r"$K = (\gamma - 1)mc^{2} = 0.25\,mc^{2}$",
                                   r"$\approx 2.2 \times 10^{16}\ \mathrm{J}$",
                                   r"for one kilogram"]),
            ),
            dict(
                text="That is roughly the energy released by a five megaton "
                     "device, to move one kilogram at six tenths of c. Push "
                     "the speed to ninety-nine per cent and the bill rises by "
                     "a factor of twenty-four. This is the practical face of "
                     "that infinity in the formula.",
                visual=dict(kind="diagram", name="energy_curve"),
            ),
        ],
    ),

    # ------------------------------------------------------------- evidence
    dict(
        title="How We Know",
        segments=[
            dict(
                text="You are entitled to ask whether any of this is true, or "
                     "merely elegant. The answer arrives from the sky "
                     "continually. Cosmic rays strike the upper atmosphere and "
                     "produce muons, some fifteen kilometres up.",
                visual=dict(kind="diagram", name="muon"),
            ),
            dict(
                text="A muon lives, on average, about two microseconds. Even "
                     "travelling at nearly the speed of light, that allows it "
                     "only about six hundred metres. It should never reach the "
                     "ground. Detectors at sea level find them in abundance.",
                visual=dict(kind="math", heading="The muon puzzle",
                            lines=[r"$\tau \approx 2.2 \ \mu\mathrm{s}$",
                                   r"$c\tau \approx 660 \ \mathrm{m}$",
                                   r"but they arrive from $15\ \mathrm{km}$"]),
            ),
            dict(
                text="Both observers explain it, and they do not explain it "
                     "the same way. From the ground, the muon's clock runs "
                     "slow, so it lives long enough. From the muon's point of "
                     "view, it lives exactly two microseconds, but the "
                     "atmosphere is contracted to a few hundred metres.",
                visual=dict(kind="math", heading="Two descriptions, one result",
                            lines=[r"ground: $\ \tau' = \gamma\tau \approx 44\ \mu\mathrm{s}$",
                                   r"muon: $\ L = L_0/\gamma \approx 750\ \mathrm{m}$",
                                   r"both agree: it arrives"]),
            ),
            dict(
                text="Particle accelerators confirm the energy relation daily. "
                     "And the satellites you use to find your way must correct "
                     "for both the speed of their clocks and the gravity they "
                     "sit in, or the position they report drifts by kilometres "
                     "within a day.",
                visual=dict(kind="bullets", heading="Confirmed continually",
                            items=["Muons reaching sea level",
                                   "Accelerator energies",
                                   "Satellite navigation clocks"]),
            ),
            dict(
                text="So there it is. Two postulates, neither of them "
                     "outlandish, and from them: the end of universal time, "
                     "clocks that disagree, lengths that depend on motion, a "
                     "speed no body can reach, and mass revealed as frozen "
                     "energy. Not because the world is strange for its own "
                     "sake, but because the world is consistent, and we had "
                     "assumed something about time that was never checked.",
                visual=dict(kind="title", main="Two postulates",
                            sub="everything else follows"),
            ),
        ],
    ),

    # ------------------------------------------------------------ what next
    dict(
        title="What Comes Next",
        segments=[
            dict(
                text="One limitation, before I stop. Everything I have shown "
                     "you applies to inertial frames: observers moving "
                     "steadily, never accelerating, and never near a "
                     "gravitating body. That is why it is called special "
                     "relativity. It is the special case.",
                visual=dict(kind="bullets", heading="The special case",
                            items=["Inertial frames only",
                                   "No acceleration",
                                   "No gravity"]),
            ),
            dict(
                text="The question that troubled me afterwards was simple. A "
                     "man in a falling lift feels no weight. A man in an "
                     "accelerating rocket feels heavy. If no experiment inside "
                     "the box can tell gravity from acceleration, perhaps they "
                     "are the same thing.",
                visual=dict(kind="bullets", heading="The equivalence principle",
                            items=["Falling: you feel weightless",
                                   "Accelerating: you feel heavy",
                                   "No experiment distinguishes them",
                                   "So treat them as one"]),
            ),
            dict(
                text="Following that thought took me ten further years, and it "
                     "ended with gravity not being a force at all, but the "
                     "curvature of the spacetime we have been discussing. That "
                     "is another lecture. But notice that it starts exactly "
                     "here, with two postulates and the willingness to doubt "
                     "something obvious.",
                visual=dict(kind="title", main="General Relativity",
                            sub="gravity as curvature -- another lecture"),
            ),
        ],
    ),
]


def all_segments():
    """Flatten to a list of (chapter_index, chapter_title, segment)."""
    out = []
    for ci, ch in enumerate(CHAPTERS):
        for si, seg in enumerate(ch["segments"]):
            out.append(dict(chapter=ci, chapter_title=ch["title"],
                            index=len(out), first_in_chapter=(si == 0), **seg))
    return out


def word_count():
    return sum(len(s["text"].split()) for s in all_segments())


if __name__ == "__main__":
    segs = all_segments()
    words = word_count()
    print(f"chapters: {len(CHAPTERS)}")
    print(f"segments: {len(segs)}")
    print(f"words:    {words}")
    print(f"estimated at 145 wpm: {words / 145:.1f} min")