// Phaser 3 Auto-Generated Sprite Scene for `jirai_neko`
import Phaser from 'phaser';

export class SpritePreviewScene extends Phaser.Scene {
  constructor() {
    super('SpritePreviewScene');
  }

  preload() {
    // Ensure Pixel Art mode in game config: render: { pixelArt: true }
    this.load.spritesheet('jirai_neko', 'sprite-sheet-alpha.png', {
      frameWidth: 256,
      frameHeight: 256
    });
  }

  create() {
    this.anims.create({
      key: 'idle',
      frames: this.anims.generateFrameNumbers('jirai_neko', { start: 0, end: 3 }),
      frameRate: 5.0,
      repeat: -1
    });
    this.anims.create({
      key: 'walk',
      frames: this.anims.generateFrameNumbers('jirai_neko', { start: 6, end: 11 }),
      frameRate: 8.0,
      repeat: -1
    });

    this.actor = this.add.sprite(400, 300, 'jirai_neko');
    this.actor.play('walk');
    this.cursors = this.input.keyboard.createCursorKeys();
  }

  update() {
    if (this.cursors.left.isDown) {
      this.actor.setFlipX(true);
      this.actor.x -= 3;
    } else if (this.cursors.right.isDown) {
      this.actor.setFlipX(false);
      this.actor.x += 3;
    }
  }
}
