interface JavaScript
{
    // Must be defined as global in javascript
    void {{ name }}.joy1d.new_vector(float z);
}

int width = 50;
int height = 200;
int cursor_radius = 5;
int loc_radius = 5;

int mid_x;
int mid_y;
int target_y;
float vy;
float loc_y = 0.;
int mouse_down = false;
float[][] triangles;

// Setup the Processing Canvas
void setup(){
  size( width, height );
  mid_x = width / 2;
  mid_y = height / 2;
  // calculate triangles
  triangles = new float[2][6];
  float b = min(width / 5., height / 5.);
  float h = sqrt(3.) * b / 2.;
  float cx = (float) mid_x;
  float cy = ((float) mid_y) / 2.;
  triangles[0][0] = cx - b / 2.;
  triangles[0][1] = cy + h / 2.;
  triangles[0][2] = cx;
  triangles[0][3] = cy - h / 2.;
  triangles[0][4] = cx + b / 2.;
  triangles[0][5] = cy + h / 2.;
  float cx = mid_x;
  float cy = mid_y * 1.5;
  triangles[1][0] = cx + b / 2.;
  triangles[1][1] = cy - h / 2.;
  triangles[1][2] = cx;
  triangles[1][3] = cy + h / 2.;
  triangles[1][4] = cx - b / 2.;
  triangles[1][5] = cy - h / 2.;
  strokeWeight( 2 );
  frameRate( 15 );
}

void move_cardinal() {
  vy = target_y / -height + 0.5;
  if (vy > 0) {
    vy = 0.5;
    target_y = 0;
  } else {
    vy = -0.5;
    target_y = height;
  }
}
 

void move_vector() {
  vy = target_y / -height + 0.5;
}

void draw_triangles(){
  for (int i=0; i < 2; i++) {
    triangle(
      triangles[i][0], triangles[i][1],
      triangles[i][2], triangles[i][3],
      triangles[i][4], triangles[i][5]);
  };
}

// Main draw loop
void draw(){
 
  // Set fill-color to grey
  fill(100);


  // fill canvas grey
  background( 100 );
  stroke(75);
  line(0, mid_y, width, mid_y);

  draw_triangles();

  // draw location
  if (abs(loc_y) == 0.5) {
    stroke(255, 0, 0);
  } else {
    stroke(0, 255, 0);
  };
  strokeWeight(5);
  line(0, (-loc_y + 0.5) * height, width, (-loc_y + 0.5) * height);
  strokeWeight(2);

  stroke(255);
  // if mouse is down
  if (mouse_down) {
    if (keyPressed) {
      if (keyCode == CONTROL) {
        move_vector();
      } else {
        move_cardinal();
      }
    } else {
      move_cardinal();
    }
    //println("joy1d: vy = " + vy);
    {{ name }}.joy1d.new_vector(vy);

    // draw vector
    line(mid_x, mid_y, mid_x, target_y);

    // send commands TODO
  };
}

void mouseDragged() {
  if (mouse_down) {
    target_y = mouseY;
  };
}

void mouseOut() {
  mouse_down = false;
}

void mousePressed() {
  target_y = mouseY;
  mouse_down = true;
}

void mouseReleased() {
  mouse_down = false;
}

void set_location(float y) {
  //println("joy1d: y = " + y);
  loc_y = y;
}
