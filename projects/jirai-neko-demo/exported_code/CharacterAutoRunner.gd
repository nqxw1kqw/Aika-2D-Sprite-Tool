# Godot 4 CharacterBody2D Script for `jirai_neko`
# Attach to a CharacterBody2D node with an AnimatedSprite2D child named `AnimatedSprite2D`.
extends CharacterBody2D

const SPEED: float = 220.0
const JUMP_VELOCITY: float = -380.0
const ATLAS_PATH: String = "res://sprite-sheet-alpha.png"

const ANIM_DATA = {
  "idle": {
    "fps": 5.0,
    "loop": true,
    "rects": [
      [
        0,
        0,
        256,
        256
      ],
      [
        256,
        0,
        256,
        256
      ],
      [
        512,
        0,
        256,
        256
      ],
      [
        768,
        0,
        256,
        256
      ]
    ]
  },
  "walk": {
    "fps": 8.0,
    "loop": true,
    "rects": [
      [
        0,
        256,
        256,
        256
      ],
      [
        256,
        256,
        256,
        256
      ],
      [
        512,
        256,
        256,
        256
      ],
      [
        768,
        256,
        256,
        256
      ],
      [
        1024,
        256,
        256,
        256
      ],
      [
        1280,
        256,
        256,
        256
      ]
    ]
  }
}

@onready var anim_sprite: AnimatedSprite2D = $AnimatedSprite2D

func _ready() -> void:
	# Crisp pixel art filter:
	anim_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_build_sprite_frames()
	anim_sprite.play("walk" if ANIM_DATA.has("walk") else ANIM_DATA.keys()[0])

func _build_sprite_frames() -> void:
	var tex: Texture2D = load(ATLAS_PATH)
	var sf := SpriteFrames.new()
	for state_name in ANIM_DATA.keys():
		var info = ANIM_DATA[state_name]
		sf.add_animation(state_name)
		sf.set_animation_speed(state_name, info["fps"])
		sf.set_animation_loop(state_name, info["loop"])
		for r in info["rects"]:
			var at := AtlasTexture.new()
			at.atlas = tex
			at.region = Rect2(r[0], r[1], r[2], r[3])
			sf.add_frame(state_name, at)
	anim_sprite.sprite_frames = sf

func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity += get_gravity() * delta
	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = JUMP_VELOCITY
	var dir := Input.get_axis("ui_left", "ui_right")
	if dir != 0:
		velocity.x = dir * SPEED
		anim_sprite.flip_h = (dir < 0)
		if ANIM_DATA.has("walk"):
			anim_sprite.play("walk")
	else:
		velocity.x = move_toward(velocity.x, 0, SPEED)
		if ANIM_DATA.has("idle"):
			anim_sprite.play("idle")
	move_and_slide()
