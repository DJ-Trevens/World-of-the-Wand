// static/game_texts.js

const GAME_TEXTS = {
    PLAYER_MOVE: [
        "Tome traces your path: You move to ({x}, {y}), now facing {direction}.",
        "The weave shifts as you step to ({x}, {y}), oriented {direction}.",
        "Your journey continues to ({x}, {y}), gaze fixed {direction}.",
        "With a soft rustle of reality, you find yourself at ({x}, {y}), looking {direction}."
    ],
    PLAYER_TURN: [
        "Tome observes: You turn to face {direction} at ({x},{y}).",
        "Your gaze shifts {direction} from your position at ({x},{y}).",
        "Oriented {direction}, you survey your surroundings from ({x},{y})."
    ],
    ACTION_FEEDBACK: {
        ACTION_QUEUED: [
            "The echoes of your command resonate...",
            "Action queued.",
            "The threads of fate shift according to your command.",
            "Tome confirms: Your will has been noted...",
            "Your command is recorded...",
        ],
        ACTION_FAILED_UNKNOWN_COMMAND: [
            "Tome seems puzzled: Your will \"{actionWord}\" is indecipherable. (Perhaps 'help' will illuminate the path?)",
            "The ancient script offers no translation for \"{actionWord}\". Try 'help'.",
            "Confusion clouds the Tome's pages. The command \"{actionWord}\" is not recognized."
        ],
        SPELL_FIZZLE_NO_MANA: [
            "Your spell fizzles, your mana reserves too low for such an incantation.",
            "A pathetic spark is all you can muster; more mana is required."
        ],
        CANNOT_DRINK_NOTHING: [
            "You try to drink, but have nothing suitable in hand.",
            "Thirst quencher needed, wizard, but what?"
        ]
    },
    LORE: {
        CONNECTION_ESTABLISHED: [
            "Tome hums: Connection to the Ethereal Plane established.",
            "The ethereal link solidifies. You are connected.",
            "A bridge forms across the aether. Connection successful."
        ],
        WELCOME: ["Tome: You have materialized. Your essence is bound to ID: {playerId}."],
        WELCOME_INITIAL: ["Tome unfurls its pages: Welcome, Wizard. The Ethereal Waves await your command."],
        INITIAL_RAIN: ["Tome notes: A chilling rain falls from the slate-grey sky."],
        POTION_DRINK_SUCCESS: [
            "Tome notes: You drink a potion, feeling invigorated!",
            "A warmth spreads through you as the potion takes effect.",
            "The vial empties, and a surge of energy courses through your veins."
        ],
        POTION_DRINK_FAIL_EMPTY: [
            "Tome sighs: Your satchel is empty of potions.",
            "You reach for a potion, but find only air.",
            "Alas, no potions remain."
        ],
        SCENE_TRANSITION_WEST: [
            "Tome scribbles: You emerge on the western edge of a new area ({scene_x},{scene_y})."
        ],
        SCENE_TRANSITION_EAST: [
            "Tome scribbles: You emerge on the eastern edge of a new area ({scene_x},{scene_y})."
        ],
        SCENE_TRANSITION_NORTH: [
            "Tome scribbles: You emerge on the northern edge of a new area ({scene_x},{scene_y})."
        ],
        SCENE_TRANSITION_SOUTH: [
            "Tome scribbles: You emerge on the southern edge of a new area ({scene_x},{scene_y})."
        ],
        VOICE_BOOM_SHOUT: [
            "Tome notes: Your voice booms, costing {manaCost} mana!"
        ],
        LACK_MANA_SHOUT: [
            "Tome warns: You lack the {manaCost} mana to project your voice so powerfully."
        ],
        PLAYER_ARRIVES: ["Tome notes: {playerName} arrives in this area."],
        PLAYER_DEPARTS: ["Tome records: {playerName} has departed this area."],
        DISCONNECTED: ["Tome wails: Disconnected! Reason: {reason}. The weave unravels!"],
        CORRUPT_MANIFESTATION_SERVER: ["Tome warns: Corrupted manifestation data from the server. Detail: {detail}"],
        MANIFESTATION_FAILED_NO_PLAYER_DATA: ["Tome warns: Manifestation failed (missing player data)."],
        FONT_SORCERY_FAILED: ["Tome sighs: Font sorcery failed. Visuals may be askew."],
        CENTERING_ERROR: ["Tome struggles: The world's perspective is lost! (Centering Error)"],
        FONT_AND_DATA_ERROR: ["Tome wails: The world's very fabric is unstable! (Font & Data Error)"],
        CHAT_SAY: ["[ {senderName} says ]: "],
        CHAT_SHOUT: ["[ SHOUT from {senderName} at {sceneCoords} ]: "],
        ACTION_BLOCKED_WALL: [ // Can be used for trees too if appropriate
            "Tome groans: You run face-first into an unyielding obstacle!"
        ],
        NPC_BLOCKED_PATH: [ // Generic for any NPC that isn't a pixie
            "Tome notes: {npcName} stands firm, blocking your path."
        ],
        BUILD_FAIL_OUT_OF_BOUNDS: [
            "Tome advises: You cannot build beyond the known world."
        ],
        BUILD_FAIL_OBSTRUCTED: [
            "Tome shakes its pages: You cannot build there, something is in the way."
        ],
        BUILD_FAIL_NO_MATERIALS: [
            "Tome sighs: You lack the stone and mortar (wall items) to construct this."
        ],
        BUILD_SUCCESS: [
            "Tome records: With effort, you erect a sturdy wall. ({walls} wall items remaining)"
        ],
        DESTROY_FAIL_OUT_OF_BOUNDS: [
            "Tome queries: Destroy what? There is nothing but void there."
        ],
        DESTROY_FAIL_NO_WALL: [
            "Tome seems confused: There is no wall there to destroy."
        ],
        DESTROY_FAIL_NO_MANA: [
            "Tome warns: You lack the {manaCost} mana to deconstruct this barrier."
        ],
        DESTROY_SUCCESS: [
            "Tome exclaims: The wall crumbles to dust! You reclaim its essence. ({walls} wall items, {manaCost} mana spent)"
        ],
        BECAME_WET_WATER: [
            "Tome ripples: You step into the water, a chilling splash against your robes!"
        ],
        BECAME_WET_RAIN: [
            "Tome dampens: The persistent rain has soaked you to the bone."
        ],
        BECAME_DRY: [
            "Tome feels lighter: You finally feel dry again."
        ],
        PIXIE_MOVED_AWAY: [
            "Tome observes: {pixieName} flits out of your path with a faint chime.",
            "The air shimmers as {pixieName} dodges your approach.",
            "{pixieName} zips aside, its wings a blur."
        ],
        PIXIE_BLOCKED_PATH: [
            "Tome notes: {pixieName} hovers defiantly, somehow blocking your way."
        ],
        PIXIE_MANA_BOOST: [
            "Tome glows faintly: Nearby pixies hum, and you feel your mana replenish by {amount}!",
            "A spark of aether from a pixie invigorates you, restoring {amount} mana."
        ],
        SEES_PIXIE_NEARBY: [
            "Tome notes: You spot {pixieName}, a Mana Pixie, shimmering faintly.",
            "A Mana Pixie, {pixieName}, darts through your field of vision.",
            "Your gaze catches upon {pixieName}, a playful Mana Pixie."
        ],
        LOOK_DIRECTION_EMPTY: [
            "Tome shows: You peer {direction}, but see nothing of particular interest.",
            "Gazing {direction}, the area seems quiet."
        ],
        LOOK_AROUND_EMPTY: [
            "Tome reflects: You survey your immediate surroundings. Nothing seems out of the ordinary."
        ],
        CHOP_FAIL_NO_TREE: [
            "Tome questions: Chop what? There is no tree there."
        ],
        CHOP_FAIL_ALREADY_CHOPPED: [
            "Tome observes: The tree is already felled, a mere stump remains."
        ],
        CHOP_FAIL_NO_MANA: [
            "Tome warns: You lack the {manaCost} mana to bring your axe (or magic) to bear against this tree."
        ],
        CHOP_SUCCESS: [
            "Tome records: With a mighty effort and {manaCost} mana, the {treeName} groans and crashes to the ground! (You gain some wood - future item)",
            "The {treeName} falls before your power, costing {manaCost} mana. (Wood acquired - future item)"
        ],
        ELF_TREE_DESTROYED_REACTION: [ // Emitted when an elf's home tree is chopped
            "A mournful cry, like the sigh of wind through broken branches, echoes from {elfName}.",
            "You feel a pang of sorrow in the air as {elfName} witnesses the destruction of their home.",
            "{elfName} lets out a soft gasp, their eyes wide with disbelief and sadness at the tree's fall."
        ]
    },
    SENSORY: {
        PIXIE_SIGHT_SHIMMER: ["You catch a brief, iridescent shimmer, like that of {npcName}."],
        PIXIE_SIGHT_DART: ["A fleeting movement in the corner of your eye suggests {npcName} is near."],
        PIXIE_SOUND_CHIME: ["A faint, melodic chime echoes from {direction}, perhaps from {npcName}."],
        PIXIE_SOUND_WINGS: ["You hear the delicate thrum of tiny wings somewhere {direction}, like those of {npcName}."],
        PIXIE_SMELL_OZONE: ["A faint scent of ozone, tinged with sweetness, drifts from {direction}. Could it be {npcName}?"],
        PIXIE_MAGIC_AURA: ["You sense a playful, tingling magical aura emanating from {direction}, a signature of {npcName}."],

        ELF_SIGHT_GRACEFUL: ["You glimpse a figure moving with uncanny grace {direction}; it must be {npcName}."],
        ELF_SIGHT_WATCHFUL: ["A pair of keen eyes, belonging to {npcName}, seem to observe you from the shadows {direction}."],
        ELF_SOUND_RUSTLE: ["A soft rustling of leaves {direction}, too deliberate for the wind, hints at {npcName}."],
        ELF_SOUND_SOFT_SONG: ["A faint, almost ethereal melody drifts from {direction}. Could it be {npcName} singing?"],
        ELF_SMELL_PINE: ["The crisp scent of pine and damp earth is stronger {direction}, a tell-tale sign of {npcName}."],
        ELF_SMELL_HERBS: ["A faint aroma of wild herbs and ancient wood wafts from {direction}. Surely {npcName} is nearby."],
        ELF_MAGIC_NATURE: ["You feel a deep, grounding connection to the natural world emanating from {direction}, the aura of {npcName}."],
        ELF_MAGIC_WARDING: ["A subtle thrum of protective magic, woven with nature's essence, suggests {npcName} is warding something {direction}."]
    },
    GENERIC: {
        LORE: ["{message}"],
        SYSTEM: ["{message}"],
        EVENT_GOOD: ["{message}"],
        EVENT_BAD: ["{message}"],
        SYSTEM_EVENT_NEGATIVE: ["{message}"],
        SENSORY_SIGHT: ["{message}"],
        SENSORY_SOUND: ["{message}"],
        SENSORY_SMELL: ["{message}"],
        SENSORY_MAGIC: ["{message}"]
    }
};

function getRandomGameText(mainKey, subKey, placeholders = {}) {
    let textPool = [];
    if (GAME_TEXTS[mainKey] && GAME_TEXTS[mainKey][subKey]) {
        textPool = GAME_TEXTS[mainKey][subKey];
    } else if (GAME_TEXTS[subKey]) { // Fallback for direct subKey access if mainKey is just a general category
        textPool = GAME_TEXTS[subKey];
    }

    if (textPool && textPool.length > 0) {
        let chosenText = textPool[Math.floor(Math.random() * textPool.length)];
        for (const ph in placeholders) {
            chosenText = chosenText.replace(new RegExp(`{${ph}}`, 'g'), placeholders[ph]);
        }
        return chosenText;
    }
    return `Missing text definition or content for: ${mainKey}.${subKey}`; // This is what you're seeing
}